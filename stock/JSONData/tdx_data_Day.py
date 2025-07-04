# encoding: utf-8
# !/usr/bin/python


import os
import sys
sys.path.append("..")
import time
from struct import *
import numpy as np
import pandas as pd
from pandas import Series
from JSONData import tdx_hdf5_api as h5a
from JSONData import realdatajson as rl
from JSONData import wencaiData as wcd
from JSONData import tdxbk
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct
from JohnsonUtil import johnson_cons as ct
import tushare as ts
import pandas_ta as ta

from JSONData import sina_data
# import numba as nb
import datetime
# import logbook

# log=logbook.Logger('TDX_day')
# log = LoggerFactory.getLogger('TDX_Day')
log = LoggerFactory.log
# log.setLevel(LoggerFactory.DEBUG)
# log.setLevel(LoggerFactory.INFO)
# log.setLevel(LoggerFactory.WARNING)
# log.setLevel(LoggerFactory.ERROR)

path_sep = os.path.sep
newdaysinit = ct.newdays_limit_days
changedays = 0
global initTdxdata, initTushareCsv
initTdxdata = 0
initTushareCsv = 0
atomStockSize = 50
# tdx_index_code_list = ['999999', '399001']
tdx_index_code_list = ['999999', '399006', '399005', '399001']
# win7rootAsus = r'D:\Program Files\gfzq'
# win10Lengend = r'D:\Program\gfzq'
# win7rootXunji = r'E:\DOC\Parallels\WinTools\zd_pazq'
# win7rootList = [win7rootAsus,win7rootXunji,win10Lengend]
# macroot = r'/Users/Johnson/Documents/Johnson/WinTools/zd_pazq'
# xproot = r'E:\DOC\Parallels\WinTools\zd_pazq'
import warnings
warnings.filterwarnings("ignore")

def get_tdx_dir():
    return cct.get_tdx_dir()
#     os_sys = cct.get_sys_system()
#     os_platform = cct.get_sys_platform()
#     if os_sys.find('Darwin') == 0:
#         log.info("DarwinFind:%s" % os_sys)
#         basedir = macroot.replace('/', path_sep).replace('\\',path_sep)
#         log.info("Mac:%s" % os_platform)

#     elif os_sys.find('Win') == 0:
#         log.info("Windows:%s" % os_sys)
#         if os_platform.find('XP') == 0:
#             log.info("XP:%s" % os_platform)
#             basedir = xproot.replace('/', path_sep).replace('\\',path_sep)  # Èç¹ûÄãµÄ°²×°Â·¾¶²»Í¬,Çë¸ÄÕâÀï
#         else:
#             log.info("Win7O:%s" % os_platform)
#             for root in win7rootList:
#                 basedir = root.replace('/', path_sep).replace('\\',path_sep)  # Èç¹ûÄãµÄ°²×°Â·¾¶²»Í¬,Çë¸ÄÕâÀï
#                 if os.path.exists(basedir):
#                     log.info("%s : path:%s" % (os_platform,basedir))
#                     break
#     if not os.path.exists(basedir):
#         log.error("basedir not exists")
#     return basedir


def get_tdx_dir_blocknew():
    return cct.get_tdx_dir_blocknew()
#     blocknew_path = get_tdx_dir() + r'/T0002/blocknew/'.replace('/', path_sep).replace('\\', path_sep)
#     return blocknew_path

basedir = get_tdx_dir()
blocknew = get_tdx_dir_blocknew()
# blocknew = r'/Users/Johnson/Documents/Johnson/WinTools/zd_pazq/T0002/blocknew'
# blocknew = 'Z:\Documents\Johnson\WinTools\zd_pazq\T0002\blocknew'
lc5_dir_sh = basedir + r'\Vipdoc\sh\fzline'
lc5_dir_sz = basedir + r'\Vipdoc\sz\fzline'
lc5_dir = basedir + r'\Vipdoc\%s\fzline'
day_dir = basedir + r'\Vipdoc\%s\lday/'
day_dir_sh = basedir + r'\Vipdoc\sh\lday/'
day_dir_sz = basedir + r'/Vipdoc/sz/lday/'
exp_path = basedir + \
    "/T0002/export/".replace('/', path_sep).replace('\\', path_sep)
day_path = {'sh': day_dir_sh, 'sz': day_dir_sz}
resample_dtype = ['d', 'w', 'm','3d','5d']
# http://www.douban.com/note/504811026/


def get_code_file_path(code, type='f'):
    if code == None:
        raise Exception("code is None")
    # os.path.getmtime(ff)
    code_u = cct.code_to_symbol(code)
    if type == 'f':
        file_path = exp_path + 'forwardp' + path_sep + code_u.upper() + ".txt"
    elif type == 'b':
        file_path = exp_path + 'backp' + path_sep + code_u.upper() + ".txt"
    else:
        return None

    return file_path


def get_kdate_data(code, start='', end='', ktype='D', index=False,ascending=False):
    '''
        write get_k_data to tdx volume *100
    '''
    if start is None:
        start = ''
    if end is None:
        end = ''
    if code.startswith('999'):
        index = True
        code = str(1000000 - int(code)).zfill(6)
    elif code.startswith('399'):
        index = True

    # df = ts.get_k_data(code=code, start=start, end=end, ktype=ktype,
    # autype='qfq', index=index, retry_count=3, pause=0.001)
    if start == '' and end != '' and end is not None:
        df = ts.get_k_data(code=code, ktype=ktype, index=index)
        df = df[df.date <= end]
    else:
        df = ts.get_k_data(code=code, start=start, end=end,
                           ktype=ktype, index=index)
    if len(df) > 0:
        df.set_index('date', inplace=True)
        df.sort_index(ascending=ascending, inplace=True)
        lastdy = df.index[0]
        if cct.get_work_hdf_status() and cct.get_today_duration(lastdy) == 0:
            df.drop(lastdy, axis=0, inplace=True)
            # print df.index
        df['volume'] = df.volume.apply(lambda x: x * 100)
    return df

def LIS_TDX(X):


    # ipdb> LIS_TDX([ 20.57,  21.35,  22.04,  22.68,  22.92,  22.98,  22.58,  22.23,21.81,  21.57])
    # ([20.57, 21.35, 22.04, 22.68, 22.92, 22.98], [0, 1, 2, 3, 4, 5])
    # ipdb> LIS_TDX([ 20.57,  21.35,  22.04,  22.68,  22.98,  22.98,  22.58,  22.23,21.81,  21.57])
    # ([20.57, 21.35, 22.04, 22.68, 22.98], [0, 1, 2, 3, 5])
    # ipdb> LIS_TDX([ 20.57,  21.35,  22.04,  22.68,  22.98,  22.96,  22.58,  22.23,21.81,  21.57])
    # ([20.57, 21.35, 22.04, 22.68, 22.96], [0, 1, 2, 3, 5])
    # ipdb> LIS_TDX([ 20.57,  21.35,  22.04,  22.68,  22.98,  22.06,  22.58,  22.23,21.81,  21.57])
    # ([20.57, 21.35, 22.04, 22.06, 22.23], [0, 1, 2, 5, 7])

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
        S.append(round(X[k],2))
        pos.append(k)
        k = P[k]
    return S[::-1], pos[::-1]

def LIS_TDX_Cum(X):
    #Lis 逐级升高,重复break
    #
    N = len(X)
    P = [0] * N
    M = [0] * (N + 1)
    L = 0
    init_break=False
    for i in range(N):
        lo = 1
        hi = L
        while lo <= hi:
            mid = (lo + hi) // 2
            if (X[M[mid]] < X[i]):
                lo = mid + 1
            else:
                #出现新低 newLow LIS ma5d               
                hi = mid - 1
                init_break = True
        if init_break:
            #出现新低 newLow LIS ma5d 
            break        
        newL = lo
        P[i] = M[newL - 1]
        M[newL] = i

        if (newL > L):
            L = newL

    S = []
    pos = []
    k = M[L]
    idx = 0
    for i in range(L - 1, -1, -1):

        if idx == 0:
            idx = k
        else:
            if k + 1 != idx:
                break
            else:
                idx = k
        S.append(round(X[k], 2))
        pos.append(k)
        k = P[k]

    return S[::-1], pos[::-1]


def get_ascending_is_monotonic_decreasing(df,increasing=True):
    if not df.index.is_monotonic_increasing:
        increasing = False
        df = df.sort_index(ascending=True)

    #return default increasing
    # if not increasing:
    #     df = df.sort_index(ascending=False)
    # no ok
    return df

def write_all_kdata_to_file(code, f_path, df=None):
    """

    Function: write_all_kdata_to_file

    Summary: InsertHere

    Examples: InsertHere

    Attributes: 

        @param (code):InsertHere

        @param (f_path):InsertHere

        @param (df) default=None: InsertHere

    Returns: InsertHere

    """
    fsize = os.path.getsize(f_path)
    if fsize != 0:
        o_file = open(f_path, 'w+')
        o_file.truncate()
        o_file.close()
    if df is None:
        df = get_kdate_data(code)
    write_tdx_tushare_to_file(code, df=df)
    print("writeCode:%s size:%s" % (code, os.path.getsize(f_path) / 50))


def custom_macd(prices, fastperiod=12, slowperiod=26, signalperiod=9):
   """
 自定义的MACD计算函数，根据指定的计算方法计算EMA，然后基于这些EMA值计算MACD值。

 :param prices: 价格数组。
 :param fastperiod: 快速EMA的周期，默认为12。
 :param slowperiod: 慢速EMA的周期，默认为26。
 :param signalperiod: 信号线的周期，默认为9。
 :return: 返回DIFF, DEA和MACD。
   """
   # 初始化EMA数组
   ema_fast = np.zeros_like(prices)
   ema_slow = np.zeros_like(prices)

   # 计算EMA
   for i in range(1, len(prices)):
       if i == 1:  # 第二日的EMA计算
            ema_fast[i] = prices[i - 1] + (prices[i] - prices[i - 1]) * 2 / (fastperiod + 1)
            ema_slow[i] = prices[i - 1] + (prices[i] - prices[i - 1]) * 2 / (slowperiod + 1)
       else:  # 第三日及以后的EMA计算
            ema_fast[i] = ema_fast[i - 1] * (fastperiod - 1) / (fastperiod + 1) + prices[i] * 2 / (fastperiod + 1)
            ema_slow[i] = ema_slow[i - 1] * (slowperiod - 1) / (slowperiod + 1) + prices[i] * 2 / (slowperiod + 1)

   # 计算DIFF
   diff = ema_fast - ema_slow

   # 计算DEA
   dea = np.zeros_like(prices)
   for i in range(1, len(prices)):
        dea[i] = ((signalperiod - 1) * dea[i - 1] + 2 * diff[i]) / (signalperiod + 1)
   # 计算MACD
   macd = 2 * (diff - dea)
   return diff, dea, macdmmm

def get_tdx_macd(df):
    if len(df) < 10:
        return df
    increasing = None
    id_cout = len(df)
    limit = 39
    if id_cout < limit:
        if  df.index.is_monotonic_increasing:
            increasing = True
            df = df.sort_index(ascending=False)
        # temp_df = df.iloc[0]
        runtimes = limit-id_cout
        df = df.reset_index()
        # for t in range(runtimes):
        #     df.loc[df.shape[0]] = temp_df

        temp = df.loc[np.repeat(df.index[-1], runtimes)].reset_index(drop=True)
        # df = df.append(temp)
        df = pd.concat([df, temp], axis=0)

        df=df.sort_index(ascending=False)
    # if  increasing:
    #     df = df.sort_index(ascending=increasing)
    # df=df.fillna(0)
    # macd=DIF，signal=DEA，hist=BAR
    #macddif -> macd macddea-> dif macd=>dea ??
    # df.loc[:, 'macddif'], df.loc[:, 'macddea'], df.loc[:, 'macd'] = ta.macd(
    # df[['macd','macddif','macddea']] = ta.macd(

    # MACD (macddif) Signal Line (macddea) MACD Histogram->MACD - Signal_Line
    # macddif (MACD line), macddea (Signal Line), and the MACD Histogram
    # MACD_12_26_9  MACDh_12_26_9  MACDs_12_26_9
    # MACD Line (MACD_12_26_9, macd): Indicates the momentum.
    # Signal Line (MACDs_12_26_9, macddea): Provides buy/sell signals when crossed by the MACD line.
    # Histogram (MACDh_12_26_9, macddif): Shows the divergence or convergence between the MACD line and the Signal line, indicating 
    df[['macd','macddif','macddea']] = ta.macd(
        df['close'], fastperiod=12, slowperiod=26, signalperiod=9) 
    df = df.fillna(0)
    df['macddif'] = round( df['macddif'], 2)
    df['macddea'] = round( df['macddea'], 2)
    df['macd'] = round( df['macd']*2, 2)
    # data['diff'].values[np.isnan(data['diff'].values)] = 0.0
    # data['dea'].values[np.isnan(data['dea'].values)] = 0.0
    # data['macd'].values[np.isnan(data['macd'].values)] = 0.0
    df['macdlast1'] = df.iloc[-1]['macd']
    df['macdlast2'] = df.iloc[-2]['macd']
    df['macdlast3'] = df.iloc[-3]['macd']
    df['macdlast4'] = df.iloc[-4]['macd']
    df['macdlast5'] = df.iloc[-5]['macd']
    df['macdlast6'] = df.iloc[-6]['macd']

    if df.index.name != 'date':
        df=df[-id_cout:].set_index('date')
    else:
        df=df[-id_cout:]

    if increasing is not None:
        df = df.sort_index(ascending=increasing)
        
    return df

def get_tdx_Exp_day_to_df(code, start=None, end=None, dl=None, newdays=None, type='f', wds=True, lastdays=3, resample='d', MultiIndex=False):
    """[summary]

    [description]

    Arguments:
        code {[type]} -- [description]

    Keyword Arguments:
        start {[type]} -- [description] (default: {None})
        end {[type]} -- [description] (default: {None})
        dl {[type]} -- [description] (default: {None})
        newdays {[type]} -- [description] (default: {None})
        type {str} -- [description] (default: {'f'})
        wds {bool} -- [description] (default: {True})
        lastdays {number} -- [description] (default: {3})
        resample {str} -- [description] (default: {'d'})
        MultiIndex {bool} -- [description] (default: {False})

    Returns:
        [type] -- [description]
    """

    # h5_fname = 'tdx_day'
    # h5_table = 'day'+'_'+'dl'
    # h5 = h5a.load_hdf_db(h5_fname, table=h5_table, code_l=codelist)
    # if h5 is not None and not h5.empty:
    #     return h5

    # dd = cct.GlobalValues().getkey(cct.tdx_hd5_name)
    dd = None
    if dd is not None:
        log.info("tdx_multi_data:%s" % (len(dd.index.get_level_values(0))))
        # df = dd.loc[dd.index.isin([code], level='code')]
        df = dd.loc[code]
    else:
        df = None

    if dl is not None:
        start = cct.last_tddate(dl)

    start = cct.day8_to_day10(start)
    end = cct.day8_to_day10(end)
    
    # if dl is not None:
    #     if dl < 70:
    #         tdx_max_int = dl
    #     else:
    #         tdx_max_int = ct.tdx_max_int_start
    # else:
    #     tdx_max_int = ct.tdx_max_int

    tdx_max_int = ct.tdx_max_int
    # max_int_end = -1 if int(tdx_max_int) > 10 else None
    # max_int_end = -1 if int(tdx_max_int) > 10 else None
    max_int_end = -1 
    if newdays is not None:
        newstockdayl = newdays
    else:
        newstockdayl = newdaysinit
    # day_path = day_dir % 'sh' if code[:1] in ['5', '6', '9'] else day_dir % 'sz'
    code_u = cct.code_to_symbol(code)
    # log.debug("code:%s code_u:%s" % (code, code_u))
    if type == 'f':
        file_path = exp_path + 'forwardp' + path_sep + code_u.upper() + ".txt"
    elif type == 'b':
        file_path = exp_path + 'backp' + path_sep + code_u.upper() + ".txt"
    else:
        return None
    
    # print file_path
    # log.debug("daypath:%s" % file_path)
    # p_day_dir = day_path.replace('/', path_sep).replace('\\', path_sep)
    # p_exp_dir = exp_dir.replace('/', path_sep).replace('\\', path_sep)
    # print p_day_dir,p_exp_dir
    global initTdxdata

    if code_u.startswith('bj'):
        write_k_data_status = False
    else:
        write_k_data_status = wds
    
    if not os.path.exists(file_path):
        # ds = Series(
        #     {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
        #      'vol': 0})
        ds = pd.DataFrame()

        tmp_df = get_kdate_data(code, start='', end='', ktype='D')
        if len(tmp_df) > 0:
            write_tdx_tushare_to_file(code, df=tmp_df, start=None, type='f')
        else:
            if initTdxdata == 0:
                log.error("file_path:not exists code:%s" % (code))
            initTdxdata += 1
            # ds.index = '2016-01-01'
            # ds = ds.fillna(0)
            return ds
    else:
        # print os.path.getsize(file_path)
        if os.path.getsize(file_path) == 0:
            write_all_kdata_to_file(code, file_path)

    # ofile = open(file_path, 'rb')
    if start is None and dl is None:
        ofile = open(file_path, 'rb')
        buf = ofile.readlines()
        ofile.close()
        num = len(buf)
        no = num
        dt_list = []
        for i in range(no):
            abuf = cct.decode_bytes_type(buf[i])
            a = abuf.split(',')
            # a = buf[i].split(',')
            # 01/15/2016,27.57,28.15,26.30,26.97,714833.15,1946604544.000
            # da=a[0].split('/')
            if len(a) < 7:
                continue
            tdate = a[0]
            if len(tdate) != 10:
                continue
            # tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
            # tdate=dt.strftime('%Y-%m-%d')
            topen = float(a[1])
            thigh = float(a[2])
            tlow = float(a[3])
            tclose = float(a[4])
            # tvol = round(float(a[5]) / 10, 2)
            tvol = float(a[5])
            amount = round(float(a[6].replace('\r\n', '')), 1)  # int
            # tpre = int(a[7])  # back
            if int(topen) == 0 or int(amount) == 0:
                continue
            dt_list.append(
                {'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose,
                 'amount': amount,
                 'vol': tvol})
            # if dt is not None and tdate < dt:
            #     break
        df = pd.DataFrame(dt_list, columns=ct.TDX_Day_columns)
        df = df[~df.date.duplicated()]
        # df.sort_index(ascending=False, inplace=True)
        if start is not None and end is not None:
            df = df[(df.date >= start) & (df.date <= end)]
            # print "startend"
        elif end is not None:
            df = df[df.date <= end]
        elif start is not None:
            df = df[df.date >= start]
        if len(df) > 0:
            df = df.set_index('date')
            df = df.sort_index(ascending=True)
            if not MultiIndex:
                # if not resample == 'd' and resample in resample_dtype:
                if not resample == 'd':
                    df = get_tdx_stock_period_to_type(df, period_day=resample)

            if resample == 'd' and (cct.get_today_duration(df.index[-1]) > 3 or df.close[-3:].max() > df.open[-3:].min() * 1.6):
                tdx_err_code = cct.GlobalValues().getkey('tdx_err_code')
                if tdx_err_code is None:
                    tdx_err_code = [code]
                    cct.GlobalValues().setkey('tdx_err_code', tdx_err_code)
                    log.error("%s dl None outdata!" % (code))
                    initTdxdata += 1
                    if write_k_data_status:
                        write_all_kdata_to_file(code, f_path=file_path)
                        df = get_tdx_Exp_day_to_df(
                            code, start=start, end=end, dl=dl, newdays=newdays, type='f', wds=False, MultiIndex=MultiIndex)
                else:
                    if not code in tdx_err_code:
                        tdx_err_code.append(code)
                        cct.GlobalValues().setkey('tdx_err_code', tdx_err_code)
                        log.error("%s dl None outdata!" % (code))
                        initTdxdata += 1
                        if write_k_data_status:
                            write_all_kdata_to_file(code, f_path=file_path)
                            df = get_tdx_Exp_day_to_df(
                                code, start=start, end=end, dl=dl, newdays=newdays, type='f', wds=False, MultiIndex=MultiIndex)
                # write_tdx_sina_data_to_file(code, df=df)
        # return df
    elif dl is not None and int(dl) == 1:
        fileSize = os.path.getsize(file_path)
        if newstockdayl != 0:
            if fileSize < atomStockSize * newstockdayl:
                return pd.Series([],dtype='float64')
        # else:
            # log.info("newsday=0:%s"(code))
        data = cct.read_last_lines(file_path, int(dl) + 3)
        data_l = data.split('\n')
        dt_list = pd.Series([],dtype='float64')
        data_l.reverse()
        log.debug("day 1:%s" % data_l)
        for line in data_l:
            a = line.split(',')
            # 01/15/2016,27.57,28.15,26.30,26.97,714833.15,1946604544.000
            # da=a[0].split('/')
            log.debug("day 1 len(a):%s a:%s" % (len(a), a))
            if len(a) == 7:
                tdate = a[0]
                if len(tdate) != 10:
                    continue
                log.debug("day 1 tdate:%s" % tdate)
                # tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
                # tdate=dt.strftime('%Y-%m-%d')
                topen = round(float(a[1]), 2)
                thigh = round(float(a[2]), 2)
                tlow = round(float(a[3]), 2)
                tclose = round(float(a[4]), 2)
                # tvol = round(float(a[5]) / 10, 2)
                tvol = round(float(a[5]), 2)
                amount = round(float(a[6].replace('\r\n', '')), 1)  # int
                # tpre = int(a[7])  # back
                if int(topen) == 0 or int(amount) == 0:
                    continue
                df = Series(
                    {'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose,
                     'amount': amount,
                     'vol': tvol})
                break
            else:
                continue
                # if dt is not None and tdate < dt:
                #     break
        # df = pd.DataFrame(dt_list, columns=ct.TDX_Day_columns)
        # df = df.set_index('date')
        return df

    else:
        if df is None or len(df) == 0:
            fileSize = os.path.getsize(file_path)
            if fileSize < atomStockSize * newstockdayl:
                return pd.Series([],dtype='float64')
            if start is None:
                if dl is None:
                    dl = 60
            else:
                if dl is None:
                    dl = int(cct.get_today_duration(start) * 5 / 7)
                    log.debug("start:%s dl:%s" % (start, dl))
            inxdl = int(dl) if int(dl) > 3 else int(dl) + 2
            data = cct.read_last_lines(file_path, inxdl)
            dt_list = []
            data_l = data.split('\n')
            if newstockdayl == 0:
                if len(data_l) < 2:
                    if write_k_data_status and resample == 'd':
                        write_all_kdata_to_file(code, file_path)
                        data = cct.read_last_lines(file_path, inxdl)
                        data_l = data.split('\n')
            data_l.reverse()
            for line in data_l:
                a = line.split(',')
                # 01/15/2016,27.57,28.15,26.30,26.97,714833.15,1946604544.000
                # da=a[0].split('/')
                if len(a) == 7:
                    tdate = a[0]
                    if len(tdate) != 10:
                        continue
                    # tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
                    # tdate=dt.strftime('%Y-%m-%d')
                    topen = round(float(a[1]), 2)
                    thigh = round(float(a[2]), 2)
                    tlow = round(float(a[3]), 2)
                    tclose = round(float(a[4]), 2)
                    tvol = round(float(a[5]), 2)
                    amount = round(float(a[6].replace('\r\n', '')), 1)  # int
                    # tpre = int(a[7])  # back
                    if int(topen) == 0 or int(amount) == 0:
                        continue
                    dt_list.append(
                        {'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose,
                         'amount': amount,
                         'vol': tvol})
                else:
                    continue
                    # if dt is not None and tdate < dt:
                    #     break

            df = pd.DataFrame(dt_list, columns=ct.TDX_Day_columns)
            df = df[~df.date.duplicated()]

        else:
            # log.error("df in Multidata:%s"%(len(df)))
            df.sort_index(ascending=False, inplace=True)

        if start is not None and end is not None:
            df = df[(df.date >= start) & (df.date <= end)]

            # print df
        elif end is not None:
            df = df[df.date <= end]

        elif start is not None:
            df = df[df.date >= start]

        if not MultiIndex and resample == 'd':
            df = compute_lastdays_percent(df, lastdays=lastdays, resample=resample)

        if len(df) > 0:

            if 'date' in df.columns:
                df = df.set_index('date')
            df = df.sort_index(ascending=True)
            if not MultiIndex:
                # if not resample == 'd' and resample in resample_dtype:
                if not resample == 'd':
                    df = get_tdx_stock_period_to_type(df, period_day=resample)
                    df = compute_lastdays_percent(df, lastdays=lastdays, resample=resample)
                    if 'date' in df.columns:
                        df = df.set_index('date')
                # df['ma5d'] = pd.rolling_mean(df.close, 5)
                # df['ma10d'] = pd.rolling_mean(df.close, 10)
                # df['ma20d'] = pd.rolling_mean(df.close, 26)
                # # df['ma60d'] = pd.rolling_mean(df.close, 60)
                # df['hmax'] = df.high[-tdx_max_int:max_int_end].max()
                # df['max5'] = df.close[-5:max_int_end].max()
                # df['lmin'] = df.low[-tdx_max_int:max_int_end].min()
                # df['min5'] = df.low[-5:max_int_end].min()
                # df['cmean'] = round(df.close[-tdx_max_int:max_int_end].mean(), 2)
                # df['hv'] = df.vol[-tdx_max_int:max_int_end].max()
                # df['lv'] = df.vol[-tdx_max_int:max_int_end].min()

            dratio = (dl - len(df)) / float(dl)
            if resample == 'd' and dratio < 0.2 and df.close[-3:].max() > df.open[-3:].min() * 1.6:

                tdx_err_code = cct.GlobalValues().getkey('tdx_err_code')
                if tdx_err_code is None:
                    tdx_err_code = [code]
                    cct.GlobalValues().setkey('tdx_err_code', tdx_err_code)
                    log.info("%s start:%s df:%s dl:%s outdata!" %
                              (code, start, len(df), dl))
                    initTdxdata += 1
                    if write_k_data_status:
                        write_all_kdata_to_file(code, file_path)
                        df = get_tdx_Exp_day_to_df(
                            code, start=start, end=end, dl=dl, newdays=newdays, type='f', wds=False, MultiIndex=MultiIndex)
                else:
                    if not code in tdx_err_code:
                        tdx_err_code.append(code)
                        cct.GlobalValues().setkey('tdx_err_code', tdx_err_code)
                        log.error("%s start:%s df:%s dl:%s outdata!" %
                                  (code, start, len(df), dl))
                        initTdxdata += 1
                        if write_k_data_status:
                            write_all_kdata_to_file(code, file_path)
                            df = get_tdx_Exp_day_to_df(
                                code, start=start, end=end, dl=dl, newdays=newdays, type='f', wds=False, MultiIndex=MultiIndex)

                # write_tdx_sina_data_to_file(code, df=df)


    # df['ma5d'] = pd.rolling_mean(df.close, 5)
    # df['ma10d'] = pd.rolling_mean(df.close, 10)
    # df['ma20d'] = pd.rolling_mean(df.close, 26)
    # df['ma60d'] = pd.rolling_mean(df.close, 60)

    #hmax -10 days max
    # df['hmax'] = df.high[-tdx_max_int:-ct.tdx_max_int_end].max()
    # df['hmax'] = df.close[:-ct.tdx_max_int_end].max()
    df = df.sort_index(ascending=True)
    # if isinstance(df,pd.DataFrame):
    # perc_couts = df.loc[:,df.columns[df.columns.str.contains('perc')]][-1:]
    # perc_couts = df.loc[:,df.columns[df.columns.str.contains('perc[1-9]{1}d', regex=True, case=False)]][-1:]
    per_couts = df.loc[:,df.columns[df.columns.str.contains('per[1-9]{1}d', regex=True, case=False)]][-1:]
    
    if len(per_couts.T) > 2:
        if resample == 'd':
            df['maxp'] = per_couts.T[1:].values.max()   #per[2-9]
            fib_c  =(per_couts.T.values > 2).sum()
        else:
            df['maxp'] = per_couts.T[:3].values.max() 
            fib_c  =(per_couts.T[:3].values > 10).sum()
        df['fib'] =   fib_c
        df['maxpcout'] =  fib_c
    else:
        df['maxp'] = 0
        df['fib'] =   0
        df['maxpcout'] =  0



    '''

    df['max5'] = df['high'].rolling(3).max()
    df['high4'] = df['high'].rolling(2).max()
    df['low4'] = df['low'].rolling(2).min()
    df['hmax'] = df['high'].rolling(5).max()
    df['lastdu4'] = df['high'].rolling(2).max()/df['low'].rolling(2).min()

    '''

    
    # df['lastdu4'] = round(max(df.high4[-1],df.max5[-1],df.hmax[-1],df.upper[-1])/(df['low4'][-1]),2)
    if len(df) > 10:
        # df['lastdu4'] = round((df.high4[-1])/(df['low4'][-1]),2)
        # df['lmin'] = df.low[-tdx_max_int:max_int_end].min()
        df['lmin'] = df.low[-ct.tdx_max_int_end:-ct.tdx_high_da].min()
        df['min5'] = df.low[-6:-1].min()
        df['cmean'] = round(df.close[-10:-ct.tdx_high_da].mean(), 2)
        df['hv'] = df.vol[-tdx_max_int:-ct.tdx_high_da].max()
        df['lv'] = df.vol[-tdx_max_int:-ct.tdx_high_da].min()
        df = df.fillna(0)

        # df = df.sort_index(ascending=False)
        if not df.index.is_monotonic_increasing:
            # increasing = False
            df = df.sort_index(ascending=True)

        if cct.get_work_time_duration():
            df['max5'] = df.close[-6:-1].max()
            df['max10'] = df.close[-10:-1].max()
            df['hmax'] = df.close[-ct.tdx_max_int_end:-ct.tdx_high_da].max()
            df['hmaxvol'] = df.vol[-ct.tdx_max_int_end:-ct.tdx_high_da].max()
            df['hmax60'] = df.close[-ct.tdx_max_int_end*2:-ct.tdx_max_int_end].max()
            df['high4'] = df.close[-5:-1].max()

            # df['hmax'] = df.high[-ct.tdx_max_int_end:-ct.tdx_high_da].max()
            # df['hmax60'] = df.high[-ct.tdx_max_int_end*2:-ct.tdx_max_int_end].max()
            # df['high4'] = df.high[-5:-1].max()
            df['low4'] = df.low[-5:-1].min()
            df['lastdu4'] = df['high4'][0] /(df['low4'][0]+0.1)



        else:
            df['max5'] = df.close[-6:-1].max()
            df['max10'] = df.close[-10:-1].max()
            # df['hmax'] = df.close[-ct.tdx_max_int_end:max_int_end].max()
            df['hmax'] = df.close[-ct.tdx_max_int_end:-ct.tdx_high_da].max()
            df['hmax60'] = df.close[-ct.tdx_max_int_end*2:-ct.tdx_max_int_end].max()
            df['high4'] = df.close[-5:-1].max()

            # df['hmax'] = df.high[-ct.tdx_max_int_end:-ct.tdx_high_da].max()
            # df['hmax60'] = df.high[-ct.tdx_max_int_end*2:-ct.tdx_max_int_end].max()
            # df['high4'] = df.high[-5:-1].max()
            df['low4'] = df.low[-5:-1].min()
            # print(df.high4[0],(df['low4'][0]))
            df['lastdu4'] = df['high4'][0] /(df['low4'][0]+0.1)

    # if len(df) > 5:
    #     df['hvdu'] = df.vol.tolist().index(df.hv[-1])+1
    #     df['hvhigh'] = df.high.tolist()[df.hvdu.values[0]-1]
    #     df['lvdu'] = df.vol.tolist().index(df.lv[-1])+1
    #     df['lvlow'] = df.close.tolist()[df.lvdu.values[0]-1]
    df = get_tdx_macd(df)
    # df = df.sort_index(ascending=False)
    return df
    # add cumin[:10]

    # if not MultiIndex :
    #     if  not isinstance(df, Series) and len(df) > 0:

    #         cumdf = df.low.cummin()[:ct.cumdays].sort_index(ascending=True)
    #         cumdf_max = df.high.cummax()[:ct.cumdays].sort_index(ascending=True)
    #         cumdfc_max = df.close.cummax()[:ct.cumdays].sort_index(ascending=True)

    #         # cumdf = df.low.cummin().sort_index(ascending=True)
    #         # cumdf_max = df.high.cummax().sort_index(ascending=True)
    #         # cumdfc_max = df.close.cummax().sort_index(ascending=True)

    #         # cum_days = 30 if len(df) > 30 else (len(df))
    #         # cumdf = df.low.cummin()[:cum_days].sort_index(ascending=True)
    #         # cumdf_max = df.high.cummax()[:cum_days].sort_index(ascending=True)
    #         # cumdfc_max = df.close.cummax()[:cum_days].sort_index(ascending=True)

    #         cum_counts = cumdf.value_counts()
    #         cum_counts_max = cumdf_max.value_counts()
    #         cum_values = cumdf.values.tolist()

    #         if len(cum_counts) > 1 :
    #             # if cum_counts.values[0] > cum_counts.values[1] * 2 and (cum_counts.values[1] < 3 or cum_counts.index[0] * 1.25 < cum_counts.index[1]) :
    #             # if cum_counts.values[0] > cum_counts.values[1] * 2 and ( (cum_values[::-1].index(cum_counts.index[1]) <> 0) or (cum_values[::-1].index(cum_counts.index[0]) < cum_values[::-1].index(cum_counts.index[1]))):

    #             if cum_counts.values[0] > cum_counts.values[1] * 2 and (cum_counts.values[1] < 3 or cum_values.index(cum_counts.index[0]) > cum_values.index(cum_counts.index[1])):
    #                 pos_price = cum_counts.index[0]
    #             else:
    #                 pos_price = cum_counts.index[1]

    #         else:
    #             # for i in (range(1,len(cum_counts)-1)):
    #             #     if cum_counts.index[i] in cumdf.values:
    #             pos_price = cum_counts.index[0]

    #         if (cum_values[::-1].index(pos_price) <> 0):
    #             cumdf_Lis = cumdf[cumdf.index >= cumdf[cumdf == pos_price ].index[-1]]
    #         else:
    #             cumdf_Lis = cumdf[cumdf.index >= cumdf[cumdf == pos_price ].index[0]]

    #         # cumdf_Lis,pos_l = LIS_TDX(cumdf.tolist())
    #         cumdf_Max_Lis = cumdf_max[cumdf_max.index >= cumdf_max[cumdf_max == cum_counts_max.index[0]].index[-1]]
    #         # cumdf_Max_Lis,pos_m = LIS_TDX(cumdf_max.tolist())

    #         # log.debug("cumdf:%s %s"%(cumdf,cum_counts))
    #         # log.debug("cumdfmax:%s %s"%(cumdf_max,cum_counts_max))
    #         # log.debug("cumdfc:%s %s"%(cumdfc_max,cumdfc_max.value_counts()))

    #         # cum_min, pos = LIS_TDX_Cum(cumdf_Lis.tolist())
    #         # log.debug("cum_min:%s pos:%s"%(cum_min,pos))

    #         # max_lastd = cumdf_max[cumdf_max == cum_counts_max.index[0]].index[-1]
    #         # cumdf_max_f = cumdf_max[cumdf_max.index >= max_lastd]
    #         # cumdf_max_f = cumdf_max_f.sort_index(ascending=False)
    #         # #print cumdf_max[-1],cum_counts_max.index[0]
    #         # cum_maxf, posf = LIS_TDX_Cum(cumdf_max_f.tolist())

    #         if len(cumdf_Lis) > 1:
    #             df['cumins'] = round(cum_counts.index[0], 2)
    #             #low price and start pos
    #             df['cumine'] = round(cumdf[-1], 2)
    #             #e end price and pos
    #             df['cumaxe'] = round(max(cumdf_max), 2)
    #             #cumax  high price max
    #             df['cumaxc'] = round(max(cumdfc_max), 2)
    #             #cumax close price max
    #             # df['cumaxs'] = round(max(cumdf_max), 2)
    #             df['cumin'] = len(cumdf_Lis)
    #         else:
    #             df['cumin'] = -len(cumdf_Max_Lis) if len(cum_counts_max) > 1 else (len(cumdf))
    #         # if len(cum_counts) > 0 and len(pos) > 0 :
    #         #     df['cumins'] = round(cum_counts.index[0], 2)
    #         #     #low price and start pos
    #         #     df['cumine'] = round(cumdf[-1], 2)
    #         #     #cumine end price and pos
    #         #     df['cumaxe'] = round(max(cumdf_max), 2)
    #         #     #cumax  high price max
    #         #     df['cumaxc'] = round(max(cumdfc_max), 2)
    #         #     #cumax close price max
    #         #     # df['cumaxs'] = round(max(cumdf_max), 2)
    #         #     # if  (round(cum_counts.index[0], 2) == cum_min[0]) and len(pos) > 1 or len(cum_counts) == len(pos) :
    #         #     import ipdb;ipdb.set_trace()

    #         #     if  (round(cum_counts.index[0], 2) <= cum_min[0]) and len(pos) > 1 or len(cum_counts) == len(pos) :
    #         #         if len(pos) == 1 and cum_min[0] == cumdf_max[-1]:
    #         #             if len(cumdf_max_f) == len(posf) and len(posf) > len(pos):
    #         #                 df['cumin'] = -len(posf)
    #         #             else:
    #         #                 df['cumin'] = len(pos)
    #         #         else:
    #         #             df['cumin'] = len(pos)
    #         #         log.debug("cumincounts:%s cum_min:%s pos:%s"%(len(pos),cum_min,pos))
    #         #     else:
    #         #         if len(cumdf_max_f) == len(posf) and len(posf) > len(pos):
    #         #             df['cumin'] = -len(posf)
    #         #         else:
    #         #             df['cumin'] = -1
    #         # else:
    #         #     if len(cumdf_max_f) == len(posf) and len(posf) > len(pos):
    #         #         df['cumin'] = -len(posf)
    #         #     else:
    #         #         df['cumin'] = -1
    #     else:
    #         df['cumin'] = 0



INDEX_LIST = {'sh': 'sh000001', 'sz': 'sz399001', 'hs300': 'sz399300',
              'sz50': 'sh000016', 'zxb': 'sz399005', 'cyb': 'sz399006'}


# def get_tdx_append_now_df_api(code, start=None, end=None, type='f'):

#     # start=cct.day8_to_day10(start)
#     # end=cct.day8_to_day10(end)
#     # print start,end
#     df = get_tdx_Exp_day_to_df(code, type, start, end).sort_index(ascending=True)
#     # print df.index.values[:1],df.index.values[-1:]
#     today = cct.get_today()

#     if len(df) > 0:
#         tdx_last_day = df.index[-1]
#     else:
#         tdx_last_day = start
#     duration = cct.get_today_duration(tdx_last_day)
#     log.debug("duration:%s"%duration)
#     log.debug("tdx_last_day:%s" % tdx_last_day)
#     index_status = False
#     code_t=None
#     if code == '999999':
#         code = 'sh'
#         index_status = True
#     elif code.startswith('399'):
#         index_status = True
#         for k in INDEX_LIST.keys():
#             if INDEX_LIST[k].find(code) > 0:
#                 code = k
#     log.debug("duration:%s" % duration)
#     if end is not None:
#         # print end,df.index[-1]
#         if len(df)==0:
#             return df
#         if end <= df.index[-1]:
#             # print(end, df.index[-1])
#             # return df
#             duration = 0
#         else:
#             today = end

#     if duration >= 1:
#         if index_status:
#             code_t = INDEX_LIST[code][2:]
#         try:
#             ds = get_kdate_data(code, start=tdx_last_day, end=today)
#             # ds = ts.get_h_data('000001', start=tdx_last_day, end=today,index=index_status)
#             # df.index = pd.to_datetime(df.index)
#         except (IOError, EOFError, Exception) as e:
#             print "Error Duration:", e
#             cct.sleep(2)
#             ds = ts.get_h_data(code_t, start=tdx_last_day, end=today, index=index_status)
#             df.index = pd.to_datetime(df.index)
#         if ds is not None and len(ds) > 1:
#             if len(df) > 0:
#                 lends = len(ds)
#             else:
#                 lends = len(ds) + 1
#             ds = ds[:lends - 1]
#             if index_status:
#                 if code == 'sh':
#                     code = '999999'
#                 else:
#                     code = code_t
#                 ds['code'] = code
#             else:
#                 ds['code'] = code
#             # ds['vol'] = 0
#             ds = ds.loc[:, ['code', 'open', 'high', 'low', 'close', 'volume', 'amount']]
#             # ds.rename(columns={'volume': 'amount'}, inplace=True)
#             ds.rename(columns={'volume': 'vol'}, inplace=True)
#             ds.sort_index(ascending=True, inplace=True)
#             log.debug("ds:%s" % ds[:1])
#             df = df.append(ds)
#             # pd.concat([df,ds],axis=0, join='outer')
#             # result=pd.concat([df,ds])

#         if cct.get_now_time_int() > 915 and cct.get_now_time_int() < 1510:
#             log.debug("get_work_time:work")
#             if end is None:
#                 # dm = rl.get_sina_Market_json('all').set_index('code')
#                 if index_status:
#                     log.debug("code:%s code_t:%s"%(code,code_t))
#                     dm = sina_data.Sina().get_stock_code_data(code_t,index=index_status)
#                     dm.code = code
#                     dm = dm.set_index('code')
#                 else:
#                     dm = sina_data.Sina().get_stock_code_data(code,index=index_status).set_index('code')
#                 log.debug("dm:%s now:%s"%(len(dm),dm))
#                 if dm is not None and df is not None and not dm.empty  and not df.empty:
#                     # dm=dm.drop_duplicates()
#                     # log.debug("not None dm:%s" % dm[-1:])
#                     dm.rename(columns={'volume': 'amount', 'turnover': 'vol'}, inplace=True)
#                     c_name=dm.loc[code,['name']].values[0]
#                     dm_code = (dm.loc[:, ['open', 'high', 'low', 'close', 'amount','vol']])
#                     log.debug("dm_code:%s" % dm_code)
#                     dm_code['amount'] = round(float(dm_code['amount']) / 100, 2)
#                     dm_code['code'] = code
#                     # dm_code['vol'] = 0
#                     dm_code['date']=today
#                     dm_code = dm_code.set_index('date')
#                     # dm_code.name = today
#                     # log.debug("dm_code_index:%s"%(dm_code))
#                     log.debug("df.open:%s dm.open%s"%(df.open[-1],round(dm.open[-1],2)))

#                     if df.open[-1] != round(dm.open[-1],2):
#                         df = df.append(dm_code)
#                     df['name']=c_name
#                     log.debug("c_name:%s df.name:%s"%(c_name,df.name[-1]))
#                     # log.debug("df[-3:]:%s" % (df[-2:]))
#                     # df['name'] = dm.loc[code, 'name']

#     if not 'name' in df.columns:
#         if index_status:
#             if code_t is None:
#                 code_t = INDEX_LIST[code][2:]
#             log.debug("code:%s code_t:%s"%(code,code_t))
#             dm = sina_data.Sina().get_stock_code_data(code_t,index=index_status)
#             dm.code = code
#             dm = dm.set_index('code')
#         else:
#             dm = sina_data.Sina().get_stock_code_data(code,index=index_status).set_index('code')
#         log.debug("dm:%s now:%s"%(len(dm),dm))
#         if dm is not None and not dm.empty:
#             c_name=dm.loc[code,['name']].values[0]
#             df['name']=c_name
#             log.debug("c_name:%s df.name:%s"%(c_name,df.name[-1:]))
#         log.debug("df:%s" % df[-3:])
#         # print df
#     # return df

def get_tdx_append_now_df_api(code, start=None, end=None, type='f', df=None, dm=None, dl=None, power=True, newdays=None, write_tushare=False, writedm=False):

    start = cct.day8_to_day10(start)
    end = cct.day8_to_day10(end)
    if start is not None and end is not None:
        dl = None
    if df is None:
        df = get_tdx_Exp_day_to_df(
            code, start=start, end=end, dl=dl, newdays=newdays).sort_index(ascending=True)
    else:
        df = df.sort_index(ascending=True)
    index_status = False

    if code == '999999':
        code_ts = str(1000000 - int(code)).zfill(6)
        index_status = True
    elif code.startswith('399'):
        index_status = True
        code_ts = code
#            for k in INDEX_LIST.keys():
#                if INDEX_LIST[k].find(code) > 0:
#                    code_ts = k
    else:
        index_status = False
        code_ts = code

    if not power:

        return get_tdx_macd(df)

    today = cct.get_today()

    if len(df) > 0:
        tdx_last_day = df.index[-1]
        if tdx_last_day == today:
            return get_tdx_macd(df)
    else:
        if start is not None:
            tdx_last_day = start
        else:
            tdx_last_day = None
#            log.warn("code :%s start is None and DF is None"%(code))
    if tdx_last_day is not None:
        duration = cct.get_today_duration(tdx_last_day)
    else:
        duration = 2
    log.debug("duration:%s" % duration)
    log.debug("tdx_last_day:%s" % tdx_last_day)
    log.debug("duration:%s" % duration)
    if end is not None:
        # print end,df.index[-1]
        if len(df) == 0:
            return df
        if end <= df.index[-1]:
            # print(end, df.index[-1])
            # return df
            duration = 0
        else:
            today = end
#    print cct.last_tddate(duration)
# if duration >= 1 and (tdx_last_day != cct.last_tddate(1) or
# cct.get_now_time_int() > 1530):
    if duration > 1 and (tdx_last_day != cct.last_tddate(1)):
        import urllib.request, urllib.error, urllib.parse
        ds = None
        try:
            ds = get_kdate_data(code_ts, start=tdx_last_day,
                                end=today, index=index_status)
            # ds['volume'] = ds.volume.apply(lambda x: x * 100)
            # ds = ts.get_h_data('000001', start=tdx_last_day, end=today,index=index_status)
            # df.index = pd.to_datetime(df.index)
        except (IOError, EOFError, Exception, urllib.error.URLError) as e:
            print("Error Duration:", e, end=' ')
            print("code:%s" % (code_ts))
            cct.sleep(0.1)
#            ds = ts.get_hist_data(code_ts, start=tdx_last_day, end=today, index=index_status)
#            df.index = pd.to_datetime(df.index)
        if ds is not None and len(ds) > 1:
            if len(df) > 0:
                lends = len(ds)
            else:
                lends = len(ds) + 1
#            if index_status:
#                if code == 'sh':
#                    code_ts = '999999'
#                else:
#                    code_ts = code_t
#                ds['code'] = int(code_ts)
#            else:
            ds['code'] = code
            ds = ds[:lends - 1]
            # print ds[:1]
#            ds['volume']=ds.volume.apply(lambda x: x * 100)
            if not 'amount' in ds.columns:
                ds['amount'] = list(map(lambda x, y, z: round(
                    (y + z) / 2 * x, 1), ds.volume, ds.high, ds.low))
            else:
                ds['amount'] = ds['amount'].apply(lambda x: round(x , 1))

            ds = ds.loc[:, ['code', 'open', 'high',
                            'low', 'close', 'volume', 'amount']]
            # ds.rename(columns={'volume': 'amount'}, inplace=True)
            ds.rename(columns={'volume': 'vol'}, inplace=True)
            ds.sort_index(ascending=True, inplace=True)
            # log.debug("ds:%s" % ds[:1])
            ds = ds.fillna(0)
            df = pd.concat([df,ds])
            if write_tushare and ((len(ds) == 1 and ds.index.values[0] != cct.get_today()) or len(ds) > 1):
                #                if index_status:
                sta = write_tdx_tushare_to_file(code, df=df)
                if sta:
                    if today == ds.index[-1]:
                        return get_tdx_macd(df)
#                else:
#                    sta=write_tdx_tushare_to_file(code,df=df)

    if cct.get_now_time_int() > 830 and cct.get_now_time_int() < 930:
        log.debug("now > 830 and <930 return")
        if isinstance(df, pd.DataFrame):
            df = df.sort_index(ascending=True)
            df['ma5d'] = pd.Series.rolling(df.close, 5).mean()
            df['ma10d'] = pd.Series.rolling(df.close, 10).mean()
            df['ma20d'] = pd.Series.rolling(df.close, 26).mean()
            df['ma60d'] = pd.Series.rolling(df.close, 60).mean()
            df = df.fillna(0)
            df = df.sort_index(ascending=False)
        return get_tdx_macd(df)
    # else:
    #     # if dm is None and not write_tushare and cct.get_work_time() and cct.get_now_time_int() < 1505:
    #     if dm is None and not write_tushare and cct.get_work_time() and cct.get_now_time_int() < 1505:
    #         return df
#    print df.index.values,code
    if dm is None and end is None:
        # if dm is None and today != df.index[-1]:
        # log.warn('today != end:%s'%(df.index[-1]))
        if index_status:
            dm = sina_data.Sina().get_stock_code_data(code, index=index_status)
#            dm.code = code
#            dm = dm.set_index('code')
        else:
            dm = sina_data.Sina().get_stock_code_data(code)

    # if duration == 0:
    #     writedm = False
    # else:
    #     writedm = True
    # writedm = False
    if df is not None and len(df) > 0:
        if df.index.values[-1] == today:
            if dm is not None and not isinstance(dm, Series):
                #                print dm.loc[code]
                dz = dm.loc[code].to_frame().T
            if index_status:
                vol_div = 1000
            else:
                vol_div = 10
            if dz.open.values[0] == df.open[-1] and 'volume' in dz.columns and int(df.vol[-1] / vol_div) == int(dz.volume.values / vol_div):
                df = df.sort_index(ascending=True)
                df['ma5d'] = pd.Series.rolling(df.close, 5).mean()
                df['ma10d'] = pd.Series.rolling(df.close, 10).mean()
                df['ma20d'] = pd.Series.rolling(df.close, 26).mean()
                df['ma60d'] = pd.Series.rolling(df.close, 60).mean()
                df = df.fillna(0)
                df = df.sort_index(ascending=False)
                return get_tdx_macd(df)
            else:
                writedm = True

    # if not writedm and cct.get_now_time_int() > 1530 or cct.get_now_time_int() < 925:
    #     return df
    if dm is not None and df is not None and not dm.empty and len(df) > 0:
        dm.rename(columns={'volume': 'vol',
                           'turnover': 'amount'}, inplace=True)
        # dm.rename(columns={'volume': 'amount', 'turnover': 'vol'}, inplace=True)
        if code not in dm.index:
            if index_status:
                if code == '999999':
                    c_name = dm.loc[code_ts, ['name']].values[0]
                    dm_code = (
                        dm.loc[code_ts, ['open', 'high', 'low', 'close', 'amount', 'vol']]).to_frame().T
                    log.error("dm index_status:%s %s %s" %
                              (code, code_ts, c_name))
            else:
                log.error("code not in index:%s %s" % (code, code_ts))
        else:
            c_name = dm.loc[code, ['name']].values[0]
            dm_code = (dm.loc[code, ['open', 'high', 'low',
                                     'close', 'amount', 'vol']]).to_frame().T
#        dm_code = (dm.loc[:, ['open', 'high', 'low', 'close', 'amount', 'vol']])
        log.debug("dm_code:%s" % dm_code)
        # dm_code['amount'] = round(float(dm_code['amount']), 2)
#        if index_status:
#            if code == 'sh':
#                code_ts = '999999'
#            else:
#                code_ts = code_t
#            dm_code['code'] = code_ts
#        else:
#            dm_code['code'] = code
        dm_code['date'] = today
        dm_code = dm_code.set_index('date')
        # log.debug("df.open:%s dm.open%s" % (df.open[-1], round(dm.open[-1], 2)))
        # print df.close[-1],round(dm.close[-1],2)
        if end is None and ((df is not None and not dm.empty) and (round(df.open[-1], 2) != round(dm.open[-1], 2)) and (round(df.close[-1], 2) != round(dm.close[-1], 2))):
            if dm.open[0] > 0 and len(df) > 0:
                if dm_code.index == df.index[-1]:
                    log.debug("app_api_dm.Index:%s df:%s" %
                              (dm_code.index.values, df.index[-1]))
                    df = df.drop(dm_code.index)
                df = pd.concat([df,dm_code])
                # df = df.astype(float)
            # df=pd.concat([df,dm],axis=0, ignore_index=True).set
        df['name'] = c_name
        log.debug("c_name:%s df.name:%s" % (c_name, df.name[-1]))

        # if not 'name' in df.columns:
        #     if index_status:
        #         if code_t is None:
        #             code_t = INDEX_LIST[code][2:]
        #         log.debug("code:%s code_t:%s"%(code,code_t))
        #         dm = sina_data.Sina().get_stock_code_data(code_t,index=index_status)
        #         dm.code = code
        #         dm = dm.set_index('code')
        #     else:
        #         dm = sina_data.Sina().get_stock_code_data(code,index=index_status).set_index('code')
        #     log.debug("dm:%s now:%s"%(len(dm),dm))
        #     if dm is not None and not dm.empty:
        #         c_name=dm.loc[code,['name']].values[0]
        #         df['name']=c_name
        #         log.debug("c_name:%s df.name:%s"%(c_name,df.name[-1:]))
        #     log.debug("df:%s" % df[-3:])
        # print df
    if len(df) > 0:
        df = df.sort_index(ascending=True)
        df['ma5d'] = pd.Series.rolling(df.close, 5).mean()
        df['ma10d'] = pd.Series.rolling(df.close, 10).mean()
        df['ma20d'] = pd.Series.rolling(df.close, 26).mean()
        df['ma60d'] = pd.Series.rolling(df.close, 60).mean()
        # df[['lower', 'ene', 'upper','bandwidth','bollpect']] = ta.bbands(df['close'], length=20, std=2, ddof=0)
        # df = df.dropna()
        df = df.fillna(0)
        df = df.sort_index(ascending=False)
    if end is None and writedm and len(df) > 0:
        if cct.get_now_time_int() < 900 or cct.get_now_time_int() > 1505:
            #            if index_status:
            sta = write_tdx_sina_data_to_file(code, df=df)
#            else:
#                sta=write_tdx_sina_data_to_file(code,df=df)
    return df


def get_tdx_append_now_df_api_tofile(code, dm=None, newdays=0, start=None, end=None, type='f', df=None, dl=10, power=True):
    #补数据power = false
    start = cct.day8_to_day10(start)
    end = cct.day8_to_day10(end)
    if df is None:
        df = get_tdx_Exp_day_to_df(
            code, start=start, end=end, dl=dl, newdays=newdays).sort_index(ascending=True)
    else:
        df = df.sort_index(ascending=True)
    index_status = False
    if code == '999999':
        code_ts = str(1000000 - int(code)).zfill(6)
        index_status = True
    elif code.startswith('399'):
        index_status = True
        code_ts = code
#            for k in INDEX_LIST.keys():
#                if INDEX_LIST[k].find(code) > 0:
#                    code_ts = k
    else:
        index_status = False
        code_ts = code

    if not power:
        return df

    if dm is not None and code in dm.index:
        today = dm.dt.loc[code]
    else:
        today = cct.get_today()
    if len(df) > 0:
        tdx_last_day = df.index[-1]
        if tdx_last_day == today:
            return df
    else:
        if start is not None:
            tdx_last_day = start
        else:
            tdx_last_day = None

    if tdx_last_day is not None:
        duration = cct.get_today_duration(tdx_last_day)

    else:
        duration = 1
    log.debug("duration:%s" % duration)
    log.debug("tdx_last_day:%s" % tdx_last_day)
    log.debug("duration:%s" % duration)
    if end is not None:
        # print end,df.index[-1]
        if len(df) == 0:
            return df
        if end <= df.index[-1]:
            # print(end, df.index[-1])
            # return df
            duration = 0
        else:
            today = end

    if duration > 1 and (tdx_last_day != cct.last_tddate(1)):
        try:
            ds = get_kdate_data(code_ts, start=tdx_last_day,
                                end=today, index=index_status)
            if ds is None:
                return df
            if index_status:
                ds['volume'] = [round(x / 100,1) for x in ds['volume']]
            # ds['volume'] = ds.volume.apply(lambda x: x * 100)
            # ds = ts.get_h_data('000001', start=tdx_last_day, end=today,index=index_status)
            # df.index = pd.to_datetime(df.index)
        except (IOError, EOFError, Exception) as e:
            print("Error Duration:", e, end=' ')
            print("code:%s" % (code))
            cct.sleep(0.1)
            # ds = ts.get_h_data(code_t, start=tdx_last_day, end=today, index=index_status)
            # df.index = pd.to_datetime(df.index)
        if ds is not None and len(ds) >= 1:
            if len(df) > 0:
                lends = len(ds)
            else:
                lends = len(ds) + 1
            ds = ds[:lends - 1]
            ds['code'] = code
#            ds['volume']=ds.volume.apply(lambda x: x * 100)
            if not 'amount' in ds.columns:
                ds['amount'] = list(map(lambda x, y, z: round(
                    (y + z) / 2  * x, 1), ds.volume, ds.high, ds.low))
                    # (y + z) / 2 /100 * x, 1), ds.volume, ds.high, ds.low))
            else:
                ds['amount'] = ds['amount'].apply(lambda x: round(x , 1))

            ds = ds.loc[:, ['code', 'open', 'high',
                            'low', 'close', 'volume', 'amount']]

            # ds.rename(columns={'volume': 'amount'}, inplace=True)
            ds.rename(columns={'volume': 'vol'}, inplace=True)
            ds.sort_index(ascending=True, inplace=True)
            ds = ds.fillna(0)
            df = pd.concat([df,ds])
            # import ipdb;ipdb.set_trace()

            # if (len(ds) == 1 and ds.index.values[0] != cct.get_today()) or len(ds) > 1:
            if (len(ds) == 1 and ((not cct.get_work_time()) or (ds.index.values[0] != cct.get_today())) ) or len(ds) > 1:
                sta = write_tdx_tushare_to_file(code, df=df)
                if sta:
                    log.info("write %s OK." % (code))
                    if today == ds.index[-1]:
                        return df
                else:
                    log.warn("write %s error." % (code))

    if cct.get_now_time_int() > 900 and cct.get_now_time_int() < 930 and len(df) > 0:
        log.debug("now > 830 and <930 return")
        df = df.sort_index(ascending=True)
        df['ma5d'] = pd.Series.rolling(df.close, 5).mean()
        df['ma10d'] = pd.Series.rolling(df.close, 10).mean()
        df['ma20d'] = pd.Series.rolling(df.close, 26).mean()
        df['ma60d'] = pd.Series.rolling(df.close, 60).mean()
        df = df.fillna(0)
        df = df.sort_index(ascending=False)
        return df
#    print df.index.values,code
    if dm is None and end is None:
        # if dm is None and today != df.index[-1]:
        # log.warn('today != end:%s'%(df.index[-1]))
        if index_status:
            dm = sina_data.Sina().get_stock_code_data(code, index=index_status)
            # dm = dm.set_index('code')
        else:
            dm = sina_data.Sina().get_stock_code_data(code)
    if len(df) != 0 and duration == 0:
        writedm = False
    else:
        writedm = True
    if df is not None and len(df) > 0:
        if df.index.values[-1] == today:
            if dm is not None and not isinstance(dm, Series) and code in dm.index:
                dz = dm.loc[code].to_frame().T
            else:
                return df
            if index_status:
                vol_div = 1000
            else:
                vol_div = 10

            if round(dz.open.values[0], 1) == round(df.open[-1], 1) and 'volume' in dz.columns and int(df.vol[-1] / vol_div) == int(dz.volume.values / vol_div):
                df = df.sort_index(ascending=True)
                df['ma5d'] = pd.Series.rolling(df.close, 5).mean()
                df['ma10d'] = pd.Series.rolling(df.close, 10).mean()
                df['ma20d'] = pd.Series.rolling(df.close, 26).mean()
                df['ma60d'] = pd.Series.rolling(df.close, 60).mean()
                df = df.fillna(0)
                df = df.sort_index(ascending=False)
                return df
            else:
                writedm = True

    if not writedm and cct.get_now_time_int() > 1530 or cct.get_now_time_int() < 925:
        return df

#    if dm is not None and df is not None and not dm.empty and len(df) >0:
    if dm is not None and not dm.empty:
        if len(dm) > 0:
            if code in dm.index:
                dm = dm.loc[code, :].to_frame().T
            else:
                dm = sina_data.Sina().get_stock_code_data(code)
                if dm is None or len(dm) == 0:
                    log.error("code is't find:%s" % (code))
                    return df
        dm.rename(columns={'volume': 'vol',
                           'turnover': 'amount'}, inplace=True)
        # dm.rename(columns={'volume': 'amount', 'turnover': 'vol'}, inplace=True)
        c_name = dm.loc[code, ['name']].values[0]
        dm_code = (dm.loc[code, ['open', 'high', 'low',
                                 'close', 'amount', 'vol']]).to_frame().T
        log.debug("dm_code:%s" % dm_code)
        # dm_code['amount'] = round(float(dm_code['amount']), 2)
        # if index_status:
        #     if code == 'sh':
        #         code_ts = '999999'
        #     else:
        #         code_ts = code_t
        #     dm_code['code'] = code_ts
        # else:
        #     dm_code['code'] = code
        dm_code['date'] = today
        dm_code = dm_code.set_index('date')
        # log.debug("df.open:%s dm.open%s" % (df.open[-1], round(dm.open[-1], 2)))
        # print df.close[-1],round(dm.close[-1],2)

        if end is None and ((df is not None and not dm.empty) and ((len(df) > 0 and round(df.open[-1], 2) != round(dm.open[-1], 2) )) or ((len(df) > 0 and round(df.close[-1], 2) != round(dm.close[-1], 2)))):
            if dm.open[0] > 0 and len(df) > 0:
                if dm_code.index[-1] == df.index[-1]:
                    log.debug("app_api_dm.Index:%s df:%s" %
                              (dm_code.index.values, df.index[-1]))
                    df = df.drop(dm_code.index)
                df = pd.concat([df,dm_code])
            elif len(dm) != 0 and len(df) == 0:
                df = dm_code
        else:
            df = dm_code
                # df = df.astype(float)
            # df=pd.concat([df,dm],axis=0, ignore_index=True).set
        df['name'] = c_name
        log.debug("c_name:%s df.name:%s" % (c_name, df.name[-1]))

    if len(df) > 5:
        df = df.sort_index(ascending=True)
        df['ma5d'] = pd.Series.rolling(df.close, 5).mean()
        df['ma10d'] = pd.Series.rolling(df.close, 10).mean()
        df['ma20d'] = pd.Series.rolling(df.close, 26).mean()
        df['ma60d'] = pd.Series.rolling(df.close, 60).mean()
        df = df.fillna(0)
        df = df.sort_index(ascending=False)

    if writedm and len(df) > 0:
        if cct.get_now_time_int() < 900 or cct.get_now_time_int() > 1505:
            df['amount'] = df['amount'].apply(lambda x: round(x , 1))
            sta = write_tdx_sina_data_to_file(code, df=df)
    return df


def write_tdx_tushare_to_file(code, df=None, start=None, type='f',rewrite=False):
    #    st=time.time()
    #    pname = 'sdata/SH601998.txt'
    # rewritefile = False
    
    code_u = cct.code_to_symbol(code)
    if code_u.startswith('bj'):
        return None
    log.debug("tushare code:%s code_u:%s" % (code, code_u))
    if type == 'f':
        file_path = exp_path + 'forwardp' + path_sep + code_u.upper() + ".txt"
    elif type == 'b':
        file_path = exp_path + 'backp' + path_sep + code_u.upper() + ".txt"
    else:
        return None

    #add 250527 johnson
    if rewrite:
        o_file = open(file_path, 'w+')
        o_file.truncate()
        o_file.close()

    if df is None:
        # df = get_tdx_Exp_day_to_df(code, newdays=0)
        ldatedf = get_tdx_Exp_day_to_df(code, dl=1, newdays=0)
        if len(ldatedf) > 0:
            lastd = ldatedf.date
        else:
            k_df = get_kdate_data(code)
            if len(k_df) > 0:
                df = k_df
            else:
                return False
        # today = cct.get_today()
        # duration = cct.get_today_duration(tdx_last_day)
        if df is None:
            if lastd == cct.last_tddate(1):
                return False
            df = get_tdx_append_now_df_api(
                code, start=start, write_tushare=False, newdays=0)
    # else:
    #     ldatedf = get_tdx_Exp_day_to_df(code, newdays=0)
    #     if len(ldatedf) < 10 and len(df) > 50:
    #         rewritefile = True

    if len(df) == 0:
        return False


    if not os.path.exists(file_path) and len(df) > 0:
        # fo = open(file_path, "w+")
        fo = open(file_path, "wb+")
#        return False
    else:
        # if rewritefile:
        #     os.remove(file_path)
        #     fo = open(file_path, "wb+")
        # else:
        fo = open(file_path, "rb+")

    fsize = os.path.getsize(file_path)
    limitpo = fsize if fsize < 150 else 150

    if not os.path.exists(file_path) or os.path.getsize(file_path) < limitpo:
        log.warn("not path:%s" % (file_path))
        return False

#    else:
#        print "no"

#    print file_path
    # fo = open(file_path, "r+")
#    os.path.getsize(file_path)
#    print fo.tell()
#    fo.seek(-limitpo,2)
#    print fo.readlines()
    if fsize != 0:
        fo.seek(-limitpo, 2)
        plist = []
        line = True
        while line:
            tmpo = fo.tell()
            line = fo.readline().decode(errors="ignore")
            alist = line.split(',')
            if len(alist) >= 7:
                if len(alist[0]) != 10:
                    continue
                tvol = round(float(alist[5]), 0)
                tamount = round(float(alist[6].split('\r')[0].replace('\r\n', '')), 0)
    #            print int(tamount)
                if fsize > 600 and (int(tvol) == 0 or int(tamount) == 0):
                    continue
    #            print line,tmpo
                if tmpo not in plist:
                    plist.append(tmpo)
        if len(plist) == 0:
            # raise Exception("data position is None")
            log.error("Exception:%s data position is None to 0" % (code))
            write_all_kdata_to_file(code, file_path)
            return False
        po = plist[-1]
        fo.seek(po)
        dater = fo.read(10).decode(errors="ignore")
        if dater.startswith('\n') and len(dater) == 10:
            po = plist[-1] + 2
            fo.seek(po)
            dater = fo.read(10).decode(errors="ignore")
        df = df[df.index >= dater]
    if len(df) >= 1:
        if fsize == 0:
            po = 0
        df = df.fillna(0)
        df.sort_index(ascending=True, inplace=True)
        fo.seek(po)
        if 'volume' in df.columns:
            df.rename(columns={'volume': 'vol'}, inplace=True)
        if not 'amount' in df.columns:
            df['amount'] = list(map(lambda x, y, z: round(
                (y + z) / 2 * x, 1), df.vol, df.high, df.low))
        else:
            df['amount'] = df['amount'].apply(lambda x: round(x , 1))

        w_t = time.time()
        wdata_list = []
        for date in df.index:
            td = df.loc[date, ['open', 'high',
                               'close', 'low', 'vol', 'amount']]
            if td.open > 0 and td.high > 0 and td.low > 0 and td.close > 0:
                tdate = str(date)[:10]
                topen = str(td.open)
                thigh = str(td.high)
                tlow = str(td.low)
                tclose = str(td.close)
                # tvol = round(float(a[5]) / 10, 2)
                tvol = str(td.vol)
                amount = str(td.amount)
                tdata = tdate + ',' + topen + ',' + thigh + ',' + tlow + \
                    ',' + tclose + ',' + tvol + ',' + amount + '\r\n'
                    # ',' + tclose + ',' + tvol + ',' + amount + '\n'
                    # ',' + tclose + ',' + tvol + ',' + amount + '\r\n'
                wdata_list.append(tdata.encode())
#        import cStringIO
#        b = cStringIO.StringIO()
#        x=0
#        while x < len(wdata_list):
#            b.write(wdata_list[x])
#            x += 1
# fo.write(b.getvalue())

        # import ipdb;ipdb.set_trace() 
        #rb+ wb+ byte bug
        fo.writelines(wdata_list)
        fo.close()
        log.info("write_done:%0.3f" % (time.time() - w_t))
        return True
    fo.close()
    return "NTrue"


def write_tdx_sina_data_to_file(code, dm=None, df=None, dl=2, type='f'):
    #    ts=time.time()
    #    if dm is None:
    #        dm = get_sina_data_df(code)
    #    if df is None:
    #        dz = dm.loc[code].to_frame().T
    #        df = get_tdx_append_now_df_api2(code,dl=dl,dm=dz,newdays=5)

    if df is None and dm is None or len(df) == 0:
        return False

    code_u = cct.code_to_symbol(code)
    log.debug("code:%s code_u:%s" % (code, code_u))
    if type == 'f':
        file_path = exp_path + 'forwardp' + path_sep + code_u.upper() + ".txt"
    elif type == 'b':
        file_path = exp_path + 'backp' + path_sep + code_u.upper() + ".txt"
    else:
        return None

    if not os.path.exists(file_path) and len(df) > 0:
        fo = open(file_path, "w+")
#        return False
    else:
        fo = open(file_path, "rb+")

    fsize = os.path.getsize(file_path)
    limitpo = fsize if fsize < 150 else 150

    if limitpo > 40:
        fo.seek(-limitpo, 2)
        plist = []
        line = True
        while line:
            tmpo = fo.tell()
            line = fo.readline().decode(errors="ignore")
            alist = line.split(',')
            if len(alist) >= 7:
                if len(alist[0]) != 10:
                    continue
                tdate = alist[0]
                tvol = round(float(alist[5]), 0)
                tamount = round(float(alist[6].split('\r')[0].replace('\r\n', '')), 0)
                # tamount = round(float(alist[6].split('\r')[0].replace('\n', '')), 0)
    #            print int(tamount)
                if fsize > 600 and (int(tvol) == 0 or int(tamount) == 0):
                    continue
    #            print line,tmpo
                if tmpo not in plist:
                    plist.append(tmpo)
    #                break
        if len(plist) == 0:
            log.error("Exception:%s data position is None to 0" % (code))
            write_all_kdata_to_file(code, file_path)
            return False
        po = plist[-1]
        fo.seek(po)
        dater = fo.read(10).decode(errors="ignore")
        if dater.startswith('\n') and len(dater) == 10:
            po = plist[-1] + 2
            fo.seek(po)
            dater = fo.read(10).decode(errors="ignore")
        df = df[df.index >= dater]

    if len(df) >= 1:
        df = df.fillna(0)
        df.sort_index(ascending=True, inplace=True)
        if limitpo > 40:
            fo.seek(po)
        w_data = []
        for date in df.index:
            td = df.loc[date, ['open', 'high',
                               'close', 'low', 'vol', 'amount']]
            tdate = date
            if len(tdate) != 10:
                continue
            topen = str(round(td.open, 2))
            thigh = str(round(td.high, 2))
            tlow = str(round(td.low, 2))
            tclose = str(round(td.close, 2))
            # tvol = round(float(a[5]) / 10, 2)
            tvol = str(round(td.vol, 2))
            amount = str(round(td.amount, 2))
            tdata = tdate + ',' + topen + ',' + thigh + ',' + tlow + \
                ',' + tclose + ',' + tvol + ',' + amount + '\r\n'
                # ',' + tclose + ',' + tvol + ',' + amount + '\n'
                # ',' + tclose + ',' + tvol + ',' + amount + '\r\n'
            w_data.append(tdata.encode())
        fo.writelines(w_data)
        fo.close()
        return True
    fo.flush()
    fo.close()
    return "NTrue"


def Write_tdx_all_to_hdf(market, h5_fname='tdx_all_df', h5_table='all', dl=300, index=False, rewrite=False):
    """[summary]

    [Write all code tdx to h5]

    Arguments:
        market {[type]} -- ['cyb','sz','sh']

    Keyword Arguments:
        h5_fname {str} -- [description] (default: {'tdx_all_df'})
        h5_table {str} -- [description] (default: {'all'})
        dl {number} -- [description] (default: {300})
        index {bool} -- [description] (default: {False})

    Returns:
        [boll] -- [write status]
    """

    time_a = time.time()
    if not h5_fname.endswith(str(dl)):
        h5_fname = h5_fname + '_' + str(dl)
        h5_table = h5_table + '_' + str(dl)
    else:
        log.error("start write index tdx data:%s" % (tdx_index_code_list))

    if market == 'all':
        index_key = tdx_index_code_list
        Write_tdx_all_to_hdf(index_key, h5_fname=h5_fname, h5_table=h5_table, dl=dl, index=True,rewrite = rewrite)
        index = False
        rewrite = False
        market = ['all']
        # market = ['cyb', 'sh', 'sz']
    if not isinstance(market, list):
        mlist = [market]
    else:
        mlist = market

    if index:
        mlist = ['inx']
    status = False

    for ma in mlist:
        dd = pd.DataFrame()
        if not index:
            df = sina_data.Sina().market(ma)
            dfcode = df.index.tolist()
        else:
            dfcode = market
        # print dfcode[:5]
        print("ma:%s dl:%s count:%s" % (ma, dl, len(dfcode)))
        # f_name = 'tdx_all_df_30'
        time_s = time.time()
        # st=h5a.get_hdf5_file(f_name, wr_mode='w', complevel=9, complib='zlib',mutiindx=True)
        # for code in dfcode[:500]:
        idx = 0
        for code in dfcode:
            # for code in dfcode:
            df = get_tdx_Exp_day_to_df(code, dl=dl, MultiIndex=True)

            # df = df[1:] # 取消最新一天数据

            # print df
            # (map(lambda x, y: y if int(x) == 0 else x, top_dif['buy'].values, top_dif['trade'].values))
            # print df.index
            idx+=1
            if idx%100 == 1:
                print(".",end='')
            if len(df) > 0:
                # df.index = map(lambda x: x.replace('-', '').replace('\n', ''), df.index)
                df.index = [x.replace('\n', '') for x in df.index]
                df.index = df.index.astype(str)
                df.index.name = 'date'
                df.index = pd.to_datetime(df.index)
                if 'code' in df.columns:
                    df.code = df.code.astype(str)

                '''sina_data MutiIndex
                df.index = df.index.astype(str)
                df.ticktime = df.ticktime.astype(str)
                # df.ticktime = map(lambda x: int(x.replace(':', '')), df.ticktime)
                df.ticktime = map(lambda x, y: str(x) + ' ' + str(y), df.dt, df.ticktime)
                df.ticktime = pd.to_datetime(df.ticktime, format='%Y-%m-%d %H:%M:%S')
                # df = df.loc[:, ['open', 'high', 'low', 'close', 'llastp', 'volume', 'ticktime']]
                df = df.loc[:, ['close', 'high', 'low', 'llastp', 'volume', 'ticktime']]
                if 'code' not in df.columns:
                   df = df.reset_index()
                if 'dt' in df.columns:
                   df = df.drop(['dt'], axis=1)
                   # df.dt = df.dt.astype(str)
                if 'name' in df.columns:
                   # df.name = df.name.astype(str)
                   df = df.drop(['name'], axis=1)
                df = df.set_index(['code', 'ticktime'])
                h5a.write_hdf_db(h5_fname, df, table=h5_table, index=False, baseCount=500, append=False, MultiIndex=True)
                log.info("hdf5 class all :%s  time:%0.2f" % (len(df), time.time() - time_s))
                '''

                # df.info()
                # if 'code' in df.columns:
                # df.drop(['code'],axis=1,inplace=True)

                df = df.sort_index(ascending=True)
                df = df.loc[:, ['code','open', 'high', 'low', 'close', 'vol', 'amount']]
                df = df.reset_index()
                df = df.set_index(['code', 'date'])
                # df = df.astype(float)
                # xcode = cct.code_to_symbol(code)
                # if len(dd) >0:
                #     print "code:%s df in :%s"%(code,code in dd.index.get_level_values('code'))
                dd = pd.concat([dd, df], axis=0)
                # print ".", len(dd)
                # st.append(xcode,df)
                # put_time = time.time()
                # st.put("df", df, format="table", append=True, data_columns=['code','date'])
                # print "t:%0.1f"%(time.time()-put_time),
                # aa[aa.index.get_level_values('code')==333]
                # st.select_column('df','code').unique()
                # %timeit st.select_column('df','code')
                # %timeit st.select('df',columns=['close'])
                # result_df = df.loc[(df.index.get_level_values('A') > 1.7) & (df.index.get_level_values('B') < 666)]
                # x.loc[(x.A>=3.3)&(x.A<=6.6)]
                # st[xcode]=df
                '''
                Traceback (most recent call last):
                  File "tdx_data_Day.py", line 3013, in <module>
                    df = get_tdx_Exp_day_to_df(code,dl=30)
                  File "tdx_data_Day.py", line 200, in get_tdx_Exp_day_to_df
                    topen = float(a[1])
                IndexError: list index out of range
                Closing remaining open files:/Volumes/RamDisk/tdx_all_df_30.h5...done
                '''
        concat_t = time.time() - time_s

        # dd = dd.loc[:,[u'open', u'high', u'low', u'close', u'vol', u'amount']]
        print(("rewrite:%s dd.concat all :%s  time:%0.2f" % (rewrite, len(dfcode), concat_t)))
        status = h5a.write_hdf_db(h5_fname, dd, table=h5_table, index=False, baseCount=500, append=False, MultiIndex=True,rewrite=rewrite)
        if status:
            print(("hdf5 write all ok:%s  atime:%0.2f wtime:%0.2f" % (len(dfcode), time.time() - time_a, time.time() - time_s - concat_t)))
        else:
            print(("hdf5 write false:%s  atime:%0.2f wtime:%0.2f" % (len(dfcode), time.time() - time_a, time.time() - time_s - concat_t)))

    return status


def Write_sina_to_tdx(market='all', h5_fname='tdx_all_df', h5_table='all', dl=300, index=False):
    """[summary]

    [description]

    Keyword Arguments:
        market {str} -- [description] (default: {'all'})
        h5_fname {str} -- [description] (default: {'tdx_all_df'})
        h5_table {str} -- [description] (default: {'all'})
        dl {number} -- [description] (default: {300})
        index {bool} -- [description] (default: {False})

    Returns:
        [type] -- [description]
    """
    h5_fname = h5_fname + '_' + str(dl)
    h5_table = h5_table + '_' + str(dl)
    status = False
    if cct.get_work_day_status() and (cct.get_now_time_int() > 1500 or cct.get_now_time_int() < 900):
        if market == 'all':
            index = False
            # mlist = ['sh', 'sz', 'cyb' ,'kcb']
            mlist = ['sh', 'sz', 'cyb']
        else:
            if index:
                mlist = ['inx']
            else:
                mlist = [market]
        # results = []
        for mk in mlist:
            time_t = time.time()
            if not index:
                df = sina_data.Sina().market(mk)
                if 'b1' in df.columns:
                    df = df[(df.b1 > 0) | (df.a1 > 0)]
            else:
                df = sina_data.Sina().get_stock_list_data(market)
            allcount = len(df)
            # df = rl.get_sina_Market_json(mk)
            # print df.loc['600581']

            print(("market:%s A:%s open:%s" % (mk, allcount, len(df))), end=' ')
            # code_list = df.index.tolist()
            # df = get_sina_data_df(code_list)


            # df.index = [x.replace('\n', '') for x in df.index]
            # df.index = df.index.astype(str)
            # df.index.name = 'date'
            # df.index = pd.to_datetime(df.index)
            # if 'code' in df.columns:
            #     df.code = df.code.astype(str)

            df.index = df.index.astype(str)
            # df.ticktime = map(lambda x: int(x.replace(':', '')), df.ticktime)
            # df.ticktime = map(lambda x, y: str(x) + ' ' + str(y), df.dt, df.ticktime)
            # df.ticktime = pd.to_datetime(df.ticktime, format='%Y-%m-%d %H:%M:%S')
            df.dt = df.dt.astype(str)
            df['dt'] = ([str(x)[:10] for x in df['dt']])

            # df = df.loc[:, ['open', 'high', 'low', 'close', 'llastp', 'volume', 'ticktime']]
            # ['code', 'date', 'open', 'high', 'low', 'close', 'vol','amount']
            df.rename(columns={'volume': 'vol', 'turnover': 'amount', 'dt': 'date'}, inplace=True)
            #write py3 all hdf need datetime
            df['date'] = pd.to_datetime(df['date'])
            df = df.loc[:, ['date', 'open', 'high', 'low', 'close', 'vol', 'amount']]
            if 'code' not in df.columns:
                df = df.reset_index()
            # if 'dt' in df.columns:
                # df = df.drop(['dt'], axis=1)
                # df.dt = df.dt.astype(str)
            # if 'name' in df.columns:
                # df.name = df.name.astype(str)
                # df = df.drop(['name'], axis=1)
            df = df.set_index(['code', 'date'])
            df = df.astype(float)
            status = h5a.write_hdf_db(h5_fname, df, table=h5_table, index=False, baseCount=500, append=False, MultiIndex=True)
            # search_Tdx_multi_data_duration(h5_fname, h5_table, df=None,code_l=code_list, start=None, end=None, freq=None, col=None, index='date',tail=1)
            if status is not None and status:
                print("Tdx writime:%0.2f" % (time.time() - time_t))
            else:
                print("Tdx no writime:%0.2f" % (time.time() - time_t))

        return status
    else:
        log.info("no work day data or < 1500")
    return status


def search_Tdx_multi_data_duration(fname='tdx_all_df_300', table='all_300', df=None,  code_l=None, start=None, end=None, freq=None, col=None, index='date',tail=0):
    """[summary]

    [description]

    Keyword Arguments:
        fname {str} -- [description] (default: {'tdx_all_df_300'})
        table {str} -- [description] (default: {'all_300'})
        df {[type]} -- [description] (default: {None})
        code_l {[type]} -- [description] (default: {None})
        start {[type]} -- [description] (default: {None})
        end {[type]} -- [description] (default: {None})
        freq {[type]} -- [description] (default: {None})
        col {[type]} -- [description] (default: {None})
        index {str} -- [description] (default: {'date'})

    Returns:
        [type] -- [description]
    """
    # h5_fname='tdx_all_df'
    # h5_table='all'
    # dl=300
    time_s = time.time()
    # h5_fname = h5_fname +'_'+str(dl)
    # h5_table = h5_table + '_' + str(dl)

    tdx_hd5_name = cct.tdx_hd5_name
    # print(f'tdx_hd5_name:{tdx_hd5_name}')
    if df is None and fname == tdx_hd5_name:
        df = cct.GlobalValues().getkey(tdx_hd5_name)
        
    if df is None:
        if start is not None and len(str(start)) < 8:
            df_tmp = get_tdx_Exp_day_to_df('999999', end=end).sort_index(ascending=False)
            start = df_tmp.index[start]
        h5 = h5a.load_hdf_db(fname, table=table, code_l=code_l, timelimit=False, MultiIndex=True)
    else:
        h5 = df.loc[df.index.isin(code_l, level='code')]

    if h5 is not None and len(h5) > 0:
        h51 = cct.get_limit_multiIndex_Row(h5, col=col, index=index, start=start, end=end)
    else:
        h51 = None
        # log.error("h5 is None")
    if fname == tdx_hd5_name:
        if h51 is not None and len(h51) > 0 and cct.GlobalValues().getkey(tdx_hd5_name) is None:
            # cct.GlobalValues()
            log.info("cct.GlobalValues().getkey(%s)" % (tdx_hd5_name))
            cct.GlobalValues().setkey(tdx_hd5_name, h51)
        else:
            log.info("cct.GlobalValues().setkey(%s) is ok" % (tdx_hd5_name))

    log.info("search_Multi_tdx time:%0.2f" % (time.time() - time_s))
    if tail == 0:
        return h51
    else:
        return h51.groupby(level=[0]).tail(tail)
# code_list = ['000001','399006','999999']
# code_list = sina_data.Sina().all.index.tolist()
# print(f'code_list:{len(code_list)}')
# df = search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', df=None,code_l=code_list, start=20170101, end=None, freq=None, col=None, index='date')
# import ipdb;ipdb.set_trace()

# print df.index.get_level_values('code').unique().shape
# print df.loc['600310']

# duration_zero=[]
# duration_other=[]

def check_tdx_Exp_day_duration(market='all'):
    duration_zero=[]
    duration_other=[]
    df = sina_data.Sina().market(market)
    df = df[df.high > 0]    
    for code in df.index:
        dd = get_tdx_Exp_day_to_df(code, dl=1) 
        duration = cct.get_today_duration(dd.date,tdx=True) if dd is not None and len(dd) > 5 else -1
        if duration == 0:
            duration_zero.append(code)
        elif duration > 0 and duration < 60:
            duration_other.append(code)
    duration_zero =list(set(duration_zero))
    duration_other = list(set(duration_other))
    print(("duration_zero:%s duration_other:%s"%(len(duration_zero),len(duration_other))))
    return duration_other

def Write_market_all_day_mp(market='all', rewrite=False,recheck=True):
    """
    rewrite True: history date ?
    rewrite False: Now Sina date

    """
    sh_index = '000002'
    dd = get_tdx_Exp_day_to_df(sh_index, dl=1)
    # log.error("Write_market_all_day_mp:%s"%(dd))
    # #fix sleep not update sina.all
    # df = sina_data.Sina().sina.all
    duration_code=check_tdx_Exp_day_duration(market)

    # print dt,dd.date
    if market == 'alla':
        rewrite = True
        market = 'all'
    # if not rewrite and len(dd) > 0:
    if not rewrite:
        if len(duration_code) == 0:
            print("Duration:%s is OK" % (len(duration_code)))
            # return False
        else:
            print("Write duration_code:%s " %(len(duration_code)))
            log.info("duration to write :%s"%(len(duration_code)))

        # fpath =  get_code_file_path(sh_index)
        # mtime = os.path.getmtime(fpath)
        # dt = cct.get_time_to_date(mtime,'%Y-%m-%d')
        # if dt == dd.date:
        #     hs = cct.get_time_to_date(mtime,'%H%M')
        #     # print hs
        #     if hs > 1500:
        #         print "Data is out:%s"%(dd.close)
        #         return False


    # duration = 300
    # if duration <= 300 :
    #     h5_fname = 'tdx_all_df' + '_' + str(300)
    #     h5_table = 'all' + '_' + str(300)
    # else:
    #     h5_fname = 'tdx_all_df' + '_' + str(900)
    #     h5_table = 'all' + '_' + str(900)
    # df = tdd.search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', df=None,code_l=code_list, start='20150501', end=None, freq=None, col=None, index='date')
    # df = tdd.search_Tdx_multi_data_duration(h5_fname, h5_table, df=None,code_l=code_list, start=None, end=None, freq=None, col=None, index='date',tail=1)
    
    # if duration == 0:
    if len(duration_code) == 0:
        dfs = search_Tdx_multi_data_duration(code_l=[sh_index],tail=1)
        mdate = dfs.reset_index().date.values
        mdate = str(mdate[0])[:10] if len(mdate) > 0 else mdate
        if mdate == dd.date:
            print("Multi_data:%s %s all writed" % (sh_index,mdate))
            return True

    # import sys;sys.exit(0)
    # start=dd.date
    # index_ts = get_kdate_data('sh',start=start)
    if market == 'all':
        mlist = ['all']
        # mlist = ['sh', 'sz', 'cyb']
        # sina_data.Sina().all
    else:
        mlist = [market]
    # if len(index_ts) > 1:
    #     print "start:%s"%(start),
    results = []

    if len(duration_code) > 0:
        for mk in mlist:
            time_t = time.time()
            df = sina_data.Sina().market(mk)
            # log.error("Write_market_all_day_mp:%s"%(df.loc['000002',['open','close','dt','ticktime']] if '000002' in df.index.values else 'No 0002'))
            # if dd.date == df.loc['000002','dt']:
            #     log.error("Pls check sina_data.Sina().market data")

            # df = getSinaAlldf(market=mk,trend=False)
            # df = rl.get_sina_Market_json(mk)
            # print df.loc['600581']

            if df is None or len(df) < 10:
                print("dsina_data f is None")
                break
            else:
                # dt = df.dt.value_counts().index[0]
                # df = df[((df.b1 > 0) | (df.a1 > 0)) & ( df.dt >= dt)]
                df = df[((df.b1 > 0) | (df.a1 > 0))]

            # code_list = df.index.tolist()
            code_list = duration_code
            dm = get_sina_data_df(code_list)
            dm = dm[((dm.open > 0) | (dm.a1 > 0))]
            print(("market:%s A:%s open_dm:%s" % (mk, len(df),len(dm))), end=' ')

            log.info('code_list:%s df:%s' % (len(code_list), len(df)))
        #        write_tdx_tushare_to_file(sh_index,index_ts)
    #        get_tdx_append_now_df_api2(code,dl=dl,dm=dz,newdays=5)
            # get_tdx_append_now_df_api_tofile('603113', dm=None, newdays=1,
            # start=None, end=None, type='f', df=None, dl=2, power=True)

            if len(dm) > 0:
                results = cct.to_mp_run_async(
                    get_tdx_append_now_df_api_tofile, code_list, dm=dm, newdays=0)

            else:
                print(("dm is not open sell:%s"%(code_list if len(code_list) <10 else len(code_list))))

            # #debug
            # for code in code_list:
            #     print("code:%s "%(code),)
            #     res=get_tdx_append_now_df_api_tofile(code,dm=dm, newdays=0)
            #     print("status:%s\t"%(len(res)),)
            #     results.append(res)
            if recheck:
                duration_code=check_tdx_Exp_day_duration(market)
                if len(duration_code) > 0 and recheck: 
                    if len(duration_code) < 30:
                        print(f'recheck duration_code:{len(duration_code)} to write')
                    else:
                        print(f'recheck duration_code write:{len(duration_code)}: {duration_code}')

                    results = cct.to_mp_run_async(
                        get_tdx_append_now_df_api_tofile, duration_code, dm=dm, newdays=0)
                    print(("market:%s A:%s open_dm:%s" % (mk, len(df),len(dm))), end=' ')

        if recheck:
            recheck = False
        print("AllWrite:%s t:%s"%(len(duration_code),round(time.time() - time_t, 2)))


#    print "market:%s is succ result:%s"%(market,results),
#    print "t:", time.time() - time_t,

    if market == 'all':
        #        write_tdx_tushare_to_file(sh_index,index_ts)
        dm_index = sina_data.Sina().get_stock_list_data(tdx_index_code_list,index=True)
        for inx in tdx_index_code_list:
            get_tdx_append_now_df_api_tofile(inx,dm=dm_index)
        print("")
        print("Index Wri 300 ok", end=' ')
        Write_sina_to_tdx(tdx_index_code_list, index=True)
        Write_sina_to_tdx(market='all')
        print("Index Wri 900 ok", end=' ')
        Write_sina_to_tdx(tdx_index_code_list, index=True,dl=900)
        Write_sina_to_tdx(market='all', h5_fname='tdx_all_df', h5_table='all', dl=900)
    print("All is ok")
    return results


def get_tdx_power_now_df(code, start=None, end=None, type='f', df=None, dm=None, dl=None):
    if code == '999999' or code.startswith('399'):
        # if dl is not None and start is None:
            # start=get_duration_Index_date(code, dt=dl)
        if start is None and dl is not None:
            start = cct.last_tddate(days=dl)
        df = get_tdx_append_now_df_api(
            code, start=start, end=end, type=type, df=df, dm=dm)
        return df
    start = cct.day8_to_day10(start)
    end = cct.day8_to_day10(end)
    if df is None:
        df = get_tdx_Exp_day_to_df(
            code, type=type, start=start, end=end, dl=dl).sort_index(ascending=True)
        if len(df) > 0:
            df['vol'] = [round(x * 10, 1) for x in df.vol.values]
        else:
            log.warn("%s df is Empty" % (code))
        if end is not None:
            return df
    else:
        df = df.sort_index(ascending=True)
    today = cct.get_today()
    if dm is None and (today != df.index[-1] or df.vol[-1] < df.vol[-2] * 0.8)and (cct.get_now_time_int() < 830 or cct.get_now_time_int() > 930):
        # log.warn('today != end:%s'%(df.index[-1]))
        dm = sina_data.Sina().get_stock_code_data(code)

    if dm is not None and df is not None and not dm.empty:
        # dm.rename(columns={'volume': 'amount', 'turnover': 'vol'}, inplace=True)
        dm.rename(columns={'volume': 'vol',
                           'turnover': 'amount'}, inplace=True)
        c_name = dm.loc[code, ['name']].values[0]
        dm_code = (
            dm.loc[:, ['open', 'high', 'low', 'close', 'amount', 'vol']])
        log.debug("dm_code:%s" % dm_code)
        # dm_code['amount'] = round(float(dm_code['amount']) / 100, 2)
        dm_code['code'] = code
        # dm_code['vol'] = 0
        dm_code['date'] = today
        dm_code = dm_code.set_index('date')
        log.debug("df.code:%s" % (code))
        log.debug("df.open:%s dm.open%s" %
                  (df.open[-1], round(dm.open[-1], 2)))
        # print df.close[-1],round(dm.close[-1],2)
        # if df.close[-1] != round(dm.close[-1], 2) and end is None:

        if end is None and ((df is not None and not dm.empty) and (round(df.open[-1], 2) != round(dm.open[-1], 2)) and (round(df.close[-1], 2) and round(dm.close[-1], 2))):
            if dm.open[0] > 0:
                if dm_code.index == df.index[-1]:
                    log.debug("app_api_dm.Index:%s df:%s" %
                              (dm_code.index.values, df.index[-1]))
                    df = df.drop(dm_code.index)
                df = pd.concat([df,dm_code])

            # print dm
            # df=pd.concat([df,dm],axis=0, ignore_index=True).set
            # print df
        df['name'] = c_name
        log.debug("c_name:%s df.name:%s" % (c_name, df.name[-1]))
    if len(df) > 0:
        df = df.sort_index(ascending=True)
        df['ma5d'] = pd.Series.rolling(df.close, 5).mean()
        df['ma10d'] = pd.Series.rolling(df.close, 10).mean()
        df['ma20d'] = pd.Series.rolling(df.close, 26).mean()
        df['ma60d'] = pd.Series.rolling(df.close, 60).mean()
        # df['ma5d'].fillna(0)
        # df['ma10d'].fillna(0)
        # df['ma20d'].fillna(0)
        # df['ma60d'].fillna(0)
        df = df.fillna(0)
        df = df.sort_index(ascending=False)
    df = get_tdx_macd(df)
    return df


def get_sina_data_df(code,index=False):

    # index_status=False

    if isinstance(code, list):
        if len(code) > 0:
            dm = sina_data.Sina().get_stock_list_data(code,index=index)
        else:
            dm=[]
            log.error("code is None:%s"%(code))
    else:
        dm = sina_data.Sina().get_stock_code_data(code,index=index)
    return dm

def get_sina_data_cname(cname,index=False):
    # index_status=False
    code = sina_data.Sina().get_cname_code(cname)
    return code

def get_sina_data_code(code,index=False):
    # index_status=False
    if not index:
        cname = sina_data.Sina().get_code_cname(code)
    else:
        cname = sina_data.Sina().get_stock_code_data(code,index=index).name[0]
    return cname

def get_sina_datadf_cnamedf(code,df,index=False,categorylimit=16):
    # index_status=False
    dm = get_sina_data_df(code)
    # ths = wcd.search_ths_data(code)
    ths = wcd.get_wencai_data(df,categorylimit=categorylimit)
    if 'close' not in df.columns:
        dd = cct.combine_dataFrame(df,dm.loc[:,['close','name']])
    else:
        dd = cct.combine_dataFrame(df,dm['name'])
    if ths is not None and 'category' in ths.columns:
        dd = cct.combine_dataFrame(dd,ths['category'])
    # cname = sina_data.Sina().get_code_cname(code)
    return dd

# print get_sina_data_cname('通合科技')
def getSinaJsondf(market='cyb', vol=ct.json_countVol, vtype=ct.json_countType):
    df = rl.get_sina_Market_json(market)
    top_now = rl.get_market_price_sina_dd_realTime(df, vol, vtype)
    return top_now


def getSinaIndexdf():
    # '''
    # # return index df,no work
    # '''
    # dm_index = sina_data.Sina().get_stock_code_data('999999,399001,399006',index=True)
    # # dm = get_sina_data_df(dm_index.index.tolist())
    # dm = cct.combine_dataFrame(dm, dm_index, col=None, compare=None, append=True, clean=True)
    dm = getSinaAlldf(market='index')
    # tdxdata = get_tdx_exp_all_LastDF_DL(
    #             dm.index.tolist(), dt=30,power=True)

    top_all, lastpTDX_DF = get_append_lastp_to_df(dm, None, dl=ct.duration_date_day, power=ct.lastPower)

    if 'lvolume' not in top_all.columns:
        top_all.rename(columns={'lvol': 'lvolume'}, inplace=True)
    # from JSONData import powerCompute as pct
    # top_all = pct.powerCompute_df(top_all.index.tolist(), dl=ct.PowerCountdl, talib=True, filter='y', index=True)

    return top_all

tdxbkdict={'近期新高':'880865','近期异动':'880884'}

def getSinaAlldf(market='cyb', vol=ct.json_countVol, vtype=ct.json_countType, filename='mnbk', table='top_now', trend=False):
    ### Sina获取 Ratio 和tdx数据
    print("initdx", end=' ')
    market_all = False
    if not isinstance(market, list):
        # m_mark = market.split(',')
        m_mark = market.split('+')
        if len(m_mark) > 1:
            # m_0 = m_mark[0]
            if len(m_mark[0]) > 12:
                m_0 = eval(m_mark[0])
            else:
                m_0 = (m_mark[0])
            market = m_mark[1]
    else:
        m_mark=[]
    if isinstance(market, list):
        code_l = market 
        df = sina_data.Sina().get_stock_list_data(code_l)

    elif market == 'rzrq':

        df = cct.get_rzrq_code()
        code_l = cct.read_to_blocknew('068')
        code_l.extend(df.code.tolist())
        code_l = list(set(code_l))
        df = sina_data.Sina().get_stock_list_data(code_l)

    elif market == 'cx':
        df = cct.get_rzrq_code(market)
    elif market == 'zxb':
        df = cct.get_tushare_market(market, renew=True, days=60)
    elif market == 'captops':
        global initTushareCsv
        if initTushareCsv == 0:
            initTushareCsv += 1
            df = cct.get_tushare_market(market=market, renew=True, days=5)
        else:
            df = cct.get_tushare_market(market, renew=False, days=5)
    elif market == 'index':
            # blkname = '061.blk'
        # df = sina_data.Sina().get_stock_code_data('999999,399001,399006',index=True)
        df = sina_data.Sina().get_stock_code_data(['999999', '399006', '399001'], index=True)

    # elif market.lower().find('indb') >=0 :
    #         # blkname = '061.blk'
    #     indb =  cct.GlobalValues().getkey('indb')
    #     if indb is None:    
    #         code_l = cct.read_to_indb().code.tolist()
    #         cct.GlobalValues().setkey('indb',code_l)
    #     else:
    #         code_l = indb
    #     df = sina_data.Sina().get_stock_list_data(code_l)

    elif market.find('blk') > 0 or market.isdigit():
            # blkname = '061.blk'

        code_l = cct.read_to_blocknew(market)
        df = sina_data.Sina().get_stock_list_data(code_l)

        # if len(code_l) > 0:
        #     df = sina_data.Sina().get_stock_list_data(code_l)
        # else:
        #     df = wcd.get_wcbk_df(filter=market, market=filename,
        #                      perpage=1000, days=ct.wcd_limit_day)
        # df = pd.read_csv(block_path,dtype={'code':str},encoding = 'gbk')
    elif market in ['bj','kcb','sh', 'sz', 'cyb']:
        df = rl.get_sina_Market_json(market)
        # df = sina_data.Sina().market(market)
    elif market in ['all']:
        df = sina_data.Sina().all
        market_all = True

    elif market in tdxbkdict.keys():
        codelist = tdxbk.get_tdx_gn_block_code(tdxbkdict[market])
        df = sina_data.Sina().get_stock_list_data(codelist)
    else:
        if filename == 'cxg':
            df = wcd.get_wcbk_df(filter=market, market=filename,
                                 perpage=1000, days=15,monitor=True)
        else:
            df = wcd.get_wcbk_df(filter=market, market=filename,
                                 perpage=1000, days=ct.wcd_limit_day,monitor=True)
        if 'code' in df.columns:
            df = df.set_index('code')
        df = sina_data.Sina().get_stock_list_data(df.index.tolist())


    if isinstance(df, pd.DataFrame) and 'code' in df.columns:
        df = df.set_index('code')

    if len(m_mark) > 1:
        dfw_codel=[]
        if not isinstance(m_0,list):
            dfw = wcd.get_wcbk_df(filter=m_0, market=filename,
                                 perpage=1000, days=ct.wcd_limit_day,monitor=True)
            if 'code' in dfw.columns:
                dfw = dfw.set_index('code')
            dfw_codel = dfw.index.tolist()
        else:
            dfw_codel = m_0
        dfw = sina_data.Sina().get_stock_list_data(dfw_codel)
        df = cct.combine_dataFrame(df,dfw,append=True)
        codelist = df.index.astype(str).tolist()
    

    if trend and isinstance(df, pd.DataFrame):
        code_l = cct.read_to_blocknew('060')
        if market == 'all':
            co_inx = [inx for inx in code_l if inx in df.index and str(inx).startswith(('6', '30', '00'))]
        elif market == 'sh':
            co_inx = [inx for inx in code_l if inx in df.index and str(inx).startswith(('6'))]
        elif market == 'sz':
            co_inx = [inx for inx in code_l if inx in df.index and str(inx).startswith(('00'))]
        elif market == 'cyb':
            co_inx = [inx for inx in code_l if inx in df.index and str(inx).startswith(('30'))]
        else:
            co_inx = [inx for inx in code_l if inx in df.index]
        
        df = df.loc[co_inx]
    # codelist=df.code.tolist()
    # cct._write_to_csv(df,'codeall')
    # top_now = get_mmarket='all'arket_price_sina_dd_realTime(df, vol, type)
#    df =  df.dropna()
    

    if isinstance(df, pd.DataFrame) and len(df) > 0:
        if 'code' in df.columns:
            df = df.set_index('code')
        codelist = df.index.astype(str).tolist()

    elif isinstance(df, list):
        codelist = df
    else:
        if not market  in ['sz','sh']:
            market = 'all'
        df = rl.get_sina_Market_json(market)
#        codelist = df.code.tolist()
#        df = df.set_index('code')
        log.error("get_sina_Market_json %s : %s" % (market, len(df)))
#    if cct.get_now_time_int() > 915:
#        if cct.get_now_time_int() > 930:
#            if 'open' in df.columns:
#                df = df[(df.open > 0)]
#        else:
#            if 'buy' in df.columns:
#                df = df[(df.buy > 0)]

        if isinstance(df, pd.DataFrame):
            codelist = df.index.astype(str).tolist()
        else:
            log.error("df isn't pd:%s" % (df))
            
#    h5_table = market if not cct.check_chinese(market) else filename
#    h5 = top_hdf_api(fname=h5_fname,table=h5_table,df=None)
    h5_fname = 'tdx_now'
    h5_table = 'all'
    time_s = time.time()

    if not market_all and market != 'index':
        dm = sina_data.Sina().get_stock_list_data(codelist)
    else:
        dm = df

    # if cct.get_work_time() or (cct.get_now_time_int() > 915) :
    # dm['percent'] = map(lambda x, y: round((x - y) / y * 100, 2), dm.close.values, dm.llastp.values)
    dm['percent'] = ((dm['close'] - dm['llastp']) / dm['llastp'] * 100).map(lambda x: round(x, 2))
    log.debug("dm percent:%s" % (dm[:1]))
    # dm['volume'] = map(lambda x: round(x / 100, 1), dm.volume.values)
    # dm['trade'] = dm['close'] if dm['b1'] ==0 else dm['b1']
    
    dm['trade'] = list(map(lambda x, y: x if int(x) > 0 else y, dm.now, dm.b1))

    dm['buy'] = list(map(lambda x, y: x if int(x) > 0 else y, dm.now, dm.b1))

    if market != 'index':
        if cct.get_now_time_int() > 915 and cct.get_now_time_int() < 926:
            # print dm[dm.code=='000001'].b1
            # print dm[dm.code=='000001'].a1
            # print dm[dm.code=='000001'].a1_v
            # print dm[dm.code=='000001'].b1_v
            dm['volume'] = list(map(lambda x, y: x + y, dm.b1_v.values, dm.b2_v.values))
            dm = dm[(dm.b1 > 0) | (dm.a1 > 0)]
            dm['b1_v'] = ((dm['b1_v'] + dm['b2_v']) / 100 / 10000).map(lambda x: round(x, 1) + 0.01)

        elif 926 < cct.get_now_time_int() < 1502 :
            # dm = dm[dm.open > 0]
            dm = dm[(dm.b1 > 0) | (dm.a1 > 0)]
            dm['b1_v'] = ((dm['b1_v']) / dm['volume'] * 100).map(lambda x: round(x, 1))

            # dm['b1_v'] = map(lambda x, y: round(x / y * 100, 1), dm['b1_v'], dm['volume'])

        else:
            dm = dm[dm.buy > 0]
            dm['b1_v'] = ((dm['b1_v']) / dm['volume'] * 100).map(lambda x: round(x, 1))

    # print 'ratio' in dm.columns
    # print time.time()-time_s
    dm['nvol'] = dm['volume']
    
    if cct.get_now_time_int() > 932 and market not in ['sh', 'sz', 'cyb']:
        dd = rl.get_sina_Market_json('all')
        if isinstance(dd, pd.DataFrame):
            dd.drop([inx for inx in dd.index if inx not in dm.index],
                    axis=0, inplace=True)
            df = dd
    if len(df) < 1 or len(dm) < 1:
        log.info("len(df):%s dm:%s" % (len(df), len(dm)))
        dm['ratio'] = 0
    else:
        if len(dm) != len(df):
            log.info("code:%s %s diff:%s" %
                     (len(dm), len(df), len(dm) - len(df))),
#        dm=pd.merge(dm,df.loc[:,['name','ratio']],on='name',how='left')
#        dm=dm.drop_duplicates('code')
        if 'ratio' in df.columns:
            dm = cct.combine_dataFrame(dm, df.loc[:, ['name', 'ratio']])
        else:
            dm = cct.combine_dataFrame(dm, df.loc[:, ['name']])
        log.info("dm combine_df ratio:%s %s" % (len(dm), len(df))),
        dm = dm.fillna(0)
    if 925 < cct.get_now_time_int() < 1502:
        dm = dm.query('b1_v > 0 or a1_v > 0')  
    if market != 'index' and (cct.get_now_time_int() > 935 or not cct.get_work_time()):
        top_now = rl.get_market_price_sina_dd_realTime(dm, vol, vtype)
    else:
        if 'code' in dm.columns:
            dm = dm.set_index('code')
        top_now = dm
        top_now['couts'] = 0
        top_now['dff'] = 0
        top_now['prev_p'] = 0
        top_now['kind'] = 0

#    h5 = h5a.write_hdf_db(h5_fname, top_now, table=h5_table)
    # top_hdf_api(fname='tdx',wr_mode='w', table=None, df=None)
    #
    # if 'time' in h5.columns:
    #     o_time = h5[h5.time <> 0].time
    #     if len(o_time) > 0:
    #         o_time = o_time[0]
    #         print time.time() - o_time
    #         if time.time() - o_time < h5_limit_time:
    #             top_now = h5
    #             return h5
    print(":%s b1>:%s it:%s" % (initTdxdata, len(top_now), round(time.time() - time_s, 1)), end=' ')
    if top_now is None or len(top_now) == 0:
        log.error("top_all is None :%s" % (top_now))
    if isinstance(top_now,pd.DataFrame) and not 'ratio' in top_now.columns:
        top_now['ratio'] = 0

    return cct.reduce_memory_usage(top_now)


def get_tdx_day_to_df(code):
    """
        »ñÈ¡¸ö¹ÉÀúÊ·½»Ò×¼ÇÂ¼
    Parameters
    ------
      code:string
                  ¹ÉÆ±´úÂë e.g. 600848
      start:string
                  ¿ªÊ¼ÈÕÆÚ format£ºYYYY-MM-DD Îª¿ÕÊ±È¡µ½APIËùÌá¹©µÄ×îÔçÈÕÆÚÊý¾Ý
      end:string
                  ½áÊøÈÕÆÚ format£ºYYYY-MM-DD Îª¿ÕÊ±È¡µ½×î½üÒ»¸ö½»Ò×ÈÕÊý¾Ý
      ktype£ºstring
                  Êý¾ÝÀàÐÍ£¬D=ÈÕkÏß W=ÖÜ M=ÔÂ 5=5·ÖÖÓ 15=15·ÖÖÓ 30=30·ÖÖÓ 60=60·ÖÖÓ£¬Ä¬ÈÏÎªD
      retry_count : int, Ä¬ÈÏ 3
                 ÈçÓöÍøÂçµÈÎÊÌâÖØ¸´Ö´ÐÐµÄ´ÎÊý
      pause : int, Ä¬ÈÏ 0
                ÖØ¸´ÇëÇóÊý¾Ý¹ý³ÌÖÐÔÝÍ£µÄÃëÊý£¬·ÀÖ¹ÇëÇó¼ä¸ôÊ±¼äÌ«¶Ì³öÏÖµÄÎÊÌâ
    return
    -------
      DataFrame
          ÊôÐÔ:ÈÕÆÚ £¬¿ªÅÌ¼Û£¬ ×î¸ß¼Û£¬ ÊÕÅÌ¼Û£¬ ×îµÍ¼Û£¬ ³É½»Á¿£¬ ¼Û¸ñ±ä¶¯ £¬ÕÇµø·ù£¬5ÈÕ¾ù¼Û£¬10ÈÕ¾ù¼Û£¬20ÈÕ¾ù¼Û£¬5ÈÕ¾ùÁ¿£¬10ÈÕ¾ùÁ¿£¬20ÈÕ¾ùÁ¿£¬»»ÊÖÂÊ
    """
    # time_s=time.time()
    # print code
    code_u = cct.code_to_symbol(code)
    day_path = day_dir % 'sh' if code[:1] in [
        '5', '6', '9'] else day_dir % 'sz'
    p_day_dir = day_path.replace('/', path_sep).replace('\\', path_sep)
    # p_exp_dir = exp_dir.replace('/', path_sep).replace('\\', path_sep)
    # print p_day_dir,p_exp_dir
    file_path = p_day_dir + code_u + '.day'
    if not os.path.exists(file_path):
        ds = Series(
            {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
             'vol': 0})
        return ds

    ofile = open(file_path, 'rb')
    buf = ofile.read().decode(errors="ignore")
    ofile.close()
    num = len(buf)
    no = int(num / 32)
    b = 0
    e = 32
    dt_list = []
    for i in range(no):
        a = unpack('IIIIIfII', buf[b:e])
        # dt=datetime.date(int(str(a[0])[:4]),int(str(a[0])[4:6]),int(str(a[0])[6:8]))
        if len(a) < 7:
            continue
        tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
        # tdate=dt.strftime('%Y-%m-%d')
        topen = float(a[1] / 100.0)
        thigh = float(a[2] / 100.0)
        tlow = float(a[3] / 100.0)
        tclose = float(a[4] / 100.0)
        amount = float(a[5] / 10.0)
        tvol = int(a[6])  # int
        tpre = int(a[7])  # back
        dt_list.append(
            {'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose, 'amount': amount,
             'vol': tvol, 'pre': tpre})
        b = b + 32
        e = e + 32
    df = pd.DataFrame(dt_list, columns=ct.TDX_Day_columns)
    df = df[~df.date.duplicated()]

    df = df.set_index('date')
    # print "time:",(time.time()-time_s)*1000
    return df


def get_duration_Index_date(code='999999', dt=None, ptype='low', dl=None, power=False):
    """[summary]

    [description]

    Keyword Arguments:
        code {str} -- [description] (default: {'999999'})
        dt {[type]} -- [description] (default: {None})
        ptype {str} -- [description] (default: {'low'})
        dl {[type]} -- [description] (default: {None})
        power {bool} -- [description] (default: {False})

    Returns:
        [type] -- [description]
    """
    if dt is not None:
        if len(str(dt)) < 8:
            dl = int(dt) + changedays
            # df = get_tdx_day_to_df(code).sort_index(ascending=False)
            df = get_tdx_append_now_df_api(
                code, power=power).sort_index(ascending=False)
            dt = get_duration_price_date(code, dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            log.info("code:%s LastDF:%s,%s" % (code,dt, dl))
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
            # df = get_tdx_day_to_df(code).sort_index(ascending=False)
            df = get_tdx_append_now_df_api(
                code, start=dt, power=power).sort_index(ascending=False)
            # dl = len(get_tdx_Exp_day_to_df(code, start=dt)) + changedays
            dl = len(df) + changedays

            dt = df[df.index <= dt].index.values[changedays] if len(df[df.index <= dt]) > 0 else df.index.values[-1]
            log.info("LastDF:%s,%s" % (dt, dl))
        return dt, dl
    if dl is not None:
        # dl = int(dl)
        df = get_tdx_append_now_df_api(
            code, start=dt, dl=dl, power=power).sort_index(ascending=False)
        # print df
        # dl = len(get_tdx_Exp_day_to_df(code, start=dt)) + changedays
        # print df[:dl].index,dl
        dt = df[:dl].index[-1]
        log.info("dl to dt:%s" % (dt))
        return dt
    return None, None


def get_duration_date(code, ptype='low', dt=None, df=None, dl=None):
    if df is None:
        df = get_tdx_day_to_df(code).sort_index(ascending=False)
        # log.debug("code:%s" % (df[:1].index))
    else:
        df = df.sort_index(ascending=False)
    if dt != None:
        if len(str(dt)) == 10:
            dz = df[df.index >= dt]
            if dl is not None:
                if len(dz) < int(dl) - changedays:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                else:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
        elif len(str(dt)) == 8:
            dt = cct.day8_to_day10(dt)
            dz = df[df.index >= dt]
            if dl is not None:
                if len(dz) < int(dl) - changedays:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                else:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
        else:
            if len(df) > int(dt):
                dz = df[:int(dt)]
            else:
                dz = df
    elif dl is not None:
        if len(df) > int(dl):
            dz = df[:int(dl)]
        else:
            dz = df
        return dz.index[-1]
    else:
        dz = df
    if ptype == 'high':
        lowp = dz.high.max()
        lowdate = dz[dz.high == lowp].index.values[-1]
        log.debug("high:%s" % lowdate)
    elif ptype == 'close':
        lowp = dz.close.min()
        lowdate = dz[dz.close == lowp].index.values[-1]
        log.debug("high:%s" % lowdate)
    else:
        lowp = dz.low.min()
        lowdate = dz[dz.close == lowp].index.values[-1]
        log.debug("low:%s" % lowdate)
    # if ptype == 'high':
    #     lowp = dz.close.max()
    #     lowdate = dz[dz.close == lowp].index.values[0]
    #     log.debug("high:%s"%lowdate)
    # else:
    #     lowp = dz.close.min()
    #     lowdate = dz[dz.close == lowp].index.values[0]
    #     log.debug("low:%s"%lowdate)
    log.debug("date:%s %s:%s" % (lowdate, ptype, lowp))
    return lowdate


def get_duration_price_date(code=None, ptype='low', dt=None, df=None, dl=None, end=None, vtype=None, filter=True,
                            power=False,resample='d'):
    # if code == "600760":
        # log.setLevel(LoggerFactory.DEBUG)
    # else:u
        # log.setLevel(LoggerFactory.ERROR)
    # if ptype == 'low' and code == '999999':
    #     log.setLevel(LoggerFactory.DEBUG)
    # else:
    #     log.setLevel(LoggerFactory.ERROR)
    if df is None and code is not None:
        # df = get_tdx_day_to_df(code).sort_index(ascending=False)
        if power:
            df = get_tdx_append_now_df_api(
                code, start=dt, end=end, dl=dl).sort_index(ascending=False)
        else:
            df = get_tdx_Exp_day_to_df(
                code, start=dt, end=end, dl=dl).sort_index(ascending=False)
    else:
        df = df.sort_index(ascending=False)
        # log.debug("code:%s" % (df[:1].index))
    # if resample.lower() != 'd':
    #     df = df
    if dt != None:
        if len(str(dt)) == 10:
            dz = df[df.index >= dt]
            if dl is not None:
                if len(dz) < int(dl) - changedays:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                else:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
        elif len(str(dt)) == 8:
            dt = cct.day8_to_day10(dt)
            dz = df[df.index >= dt]
            if len(dz) > 0 and dl is not None:
                if len(dz) < int(dl) - changedays:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                else:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
            else:
                # log.error("code:%s dt:%s no data"%(code,dt))
                if not filter:
                    index_d = df.index[0]

        else:
            if len(df) > int(dt):
                dz = df[:int(dt)]
            else:
                dz = df
    elif dl is not None:
        if len(df) > int(dl) + 1:
            dz = df[:int(dl)]
        else:
            dz = df
        if not filter:
            if len(dz) > 0:
                index_d = dz[:1].index.values[0]
            else:
                index_d = cct.get_today()
                lowdate = cct.get_today()
                log.error("code:%s dz:%s" % (code, dz))
                if filter:
                    return lowdate
                elif not power:
                    return lowdate, index_d
                else:
                    return lowdate, index_d, pd.DataFrame()
    else:
        dz = df
    if len(dz) > 0:
        if ptype == 'high':
            lowp = dz.high.max()
            lowdate = dz[dz.high == lowp].index.values[-1]
            log.debug("high:%s" % lowdate)
        elif ptype == 'close':
            lowp = dz.close.min()
            lowdate = dz[dz.close == lowp].index.values[-1]
            log.debug("high:%s" % lowdate)
        else:
            lowp = dz.low.min()
            lowdate = dz[dz.low == lowp].index.values[-1]
            log.debug("low:%s" % lowdate)
        log.debug("date:%s %s:%s" % (lowdate, ptype, lowp))
    else:
        lowdate = df.index[0]
    # if ptype == 'high':
    #     lowp = dz.close.max()
    #     lowdate = dz[dz.close == lowp].index.values[0]
    #     log.debug("high:%s"%lowdate)
    # else:
    #     lowp = dz.close.min()
    #     lowdate = dz[dz.close == lowp].index.values[0]
    #     log.debug("low:%s"%lowdate)
    if filter:
        return lowdate
    elif not power:
        return lowdate, index_d
    else:
        return lowdate, index_d, df


def compute_power_tdx_df(tdx_df,dd):
    if len(tdx_df) >= 5:
        # idxdf = tdx_df.red[tdx_df.red <0]
        # if len(idxdf) >1:
        #     idx = tdx_df.red[tdx_df.red <0].argmax()
        # else:
        #     if len(tdx_df.red[tdx_df.red >0]) == 0:
        #         return dd
        #     else:
        #         idx = tdx_df.red[tdx_df.red >0].index[0]
        # trend = tdx_df[tdx_df.index >= idx]
        # fibl = len(trend)
        # idxh = tdx_df.high.argmax()
        idxl = tdx_df.low.idxmin()
        idxh = tdx_df.low.idxmax()
        idxl_date=tdx_df.index.tolist().index(idxl)
        idxh_date=tdx_df.index.tolist().index(idxh)

        # tdx_df.query('low == low.min() and high == high.min()')  # highest lowest
        # tdx_df[idxh_date:].query('high > high.shift(1)*0.998')   #low highest 
        # fibh = len(tdx_df[tdx_df.index >= idxh])
        # fibh = len(tdx_df[idx_date:].query('percent > 0'))

        fibh = len(tdx_df[idxl_date:].query('high > high.shift(1)*0.998 or close > close.shift(1)'))
        # vratio = -1
        # if fibl > 1:
        #     vratio = round(((trend.close[-1] - trend.close[0])/trend.close[0]*100)/fibl,1)


        # dd['op'] = int(len(LIS_TDX(tdx_df.close)[1])/float(len(tdx_df.close))*10)
        # dd['fib'] = fibl
        dd['fibl'] = fibh
        # dd['ldate'] = idx
        dd['boll'] = dd.upperL[0]
        # dd['df2'] = dd.upperT[0]
        dd['ra'] = dd.upperT[0]
        dd['kdj'] = 1
        dd['macd'] = 1
        dd['rsi'] = 1
        dd['ma'] = 1
        dd['oph'] = 1
        dd['rah'] = 1
    else:
        dd['op'] = -1
        dd['ra'] = -1
        dd['fib'] = -1
        dd['fibl'] = -1
        dd['ldate'] = -1
        dd['boll'] = -1
        dd['kdj'] = -1
        dd['macd'] = -1
        dd['rsi'] = -1
        # dd['df2'] = -1
        dd['ma'] = -1
        dd['oph'] = -1
        dd['rah'] = -1
        # log.error("tdx_df is no 9:%s"%(dd.code[0]))
    return dd


def dataframe_mode_round(df):
    roundlist = [1, 0]
    df_mode = []
    for i in roundlist:
        df_mode = df.apply(lambda x: round(x, i)).mode()
        if len(df_mode) > 0:
            break
    return df_mode


def compute_condition_up_sample(df):
    condition_up = df['low'] > df['high'].shift()        #向上跳空缺口
    condition_down = df['high'] < df['low'].shift()      #向下跳空缺口

    # df['hop'] = np.nan
    # df['hop_up'] = 101
    # df['hop_down'] = 101

    df.loc[condition_up,'hop_up'] = -1
    df.loc[condition_down,'hop_down'] =1

    hop_record=[]
    #向上跳空,看是否有回落(之后的最低价有没有低于缺口前价格)
    #向下跳空,看是否有回升(之后的最高价有没有高于缺口前价格)
    for i in range(len(df)):
        #如果向上跳空
        if list(df['hop_up'].at[i].values()) == -1:     #at loc index 
            hop_date = df['date'].at[i] #跳空时间 
            ex_hop_price = df['high'].at[i -1]  #前一根K线最高价   
            post_hop_price = df['low'].at[i]  #跳空后的价格
            fill_data = ''
            #看滞后有没有回补向上的跳空
            for j in range(i,len(df)):
                if df['low'].at[j] <= ex_hop_price:
                    fill_data = df['date'].at[i]
                    break
            hop_record.append({'hop':'up',
                                'jop_date':hop_date,
                                'ex_hop_price':ex_hop_price,
                                'post_hop_price':post_hop_price,
                                'fill_data':fill_data })
        #如果有向下跳空
        elif df['hop_down'].at[i] == 1:
            hop_date = df['date'].at[i] #跳空时间
            ex_hop_price = df['low'].at[i -1] #前一根K线最低价   
            post_hop_price = df['high'].at[i]  #跳空后的价格
            fill_data = ''
            #看之后有没有回补向下的跳空
            for j in rang(i,len(df)):
                if df['high'].at[j] >= ex_hop_price:
                    fill_data = df['date'].at[j]
                    break

            hop_record.append({'hop':'down',
                                'jop_date':hop_date,
                                'ex_hop_price':ex_hop_price,
                                'post_hop_price':post_hop_price,
                                'fill_data':fill_data })

    hop_df = pd.DataFrame(hop_record)
    return hop_df

def compute_condition_up(df):
    condition_up = df[df['low'] > df['high'].shift(1)]       #向上跳空缺口
    condition_down = df[df['high'] < df['low'].shift(1)]
          #向下跳空缺口
    # df = df.assign(hop=np.nan)

    # df.loc[condition_up,'hop_up'] = -1
    # df.loc[condition_down,'hop_down'] =1

    hop_record= []

    # hop_record=[{'hop':np.nan,
    #             'jop_date':np.nan,
    #             'ex_hop_price':np.nan,
    #             'post_hop_price':np.nan,
    #             'fill_data':np.nan,
    #             'fill_day':np.nan }]
    # hop_record_up=[]
    # hop_record_down=[]
    #向上跳空,看是否有回落(之后的最低价有没有低于缺口前价格)
    #向下跳空,看是否有回升(之后的最高价有没有高于缺口前价格)
    for i in condition_up.index:
        #如果向上跳空

        hop_date = i #跳空时间 
        # lastday = cct.day_last_days(i,-1)
        lastday = df.index[df.index < i][-1]

        ex_hop_price = df['high'].at[lastday]  #前一根K线最高价   
        post_hop_price = df['low'].at[i]  #跳空后的价格

        fill_data = ''          #回补时间
        fill_day = np.nan           #回补天数
        #看滞后有没有回补向上的跳空
        duration = df.index[df.index > i] #跳空后的数据日

        for j in duration:

            if df['low'].at[j] <= ex_hop_price:
                fill_data = j
                fill_day = len(df.index[(df.index > i) & (df.index <= j)])
                break
        hop_record.append({'hop':'up',
                            'jop_date':hop_date,
                            'ex_hop_price':ex_hop_price,
                            'post_hop_price':post_hop_price,
                            'fill_data':fill_data,
                            'fill_day':fill_day })

        #如果有向下跳空
    for i in condition_down.index:
        #如果向下跳空

        hop_date = i #跳空时间 
        # lastday = cct.day_last_days(i,-1)
        lastday = df.index[df.index < i][-1]
        ex_hop_price = df['low'].at[lastday]  #前一根K线最低价   
        post_hop_price = df['high'].at[i]  #跳空后的价格

        fill_data = ''          #回补时间
        fill_day = np.nan           #回补天数
        #看滞后有没有回补向上的跳空
        duration = df.index[df.index > i] #跳空后的数据日
        
        for j in duration:
            if df['low'].at[j] >= ex_hop_price:
                fill_data = j
                fill_day = len(df.index[(df.index > i) & (df.index <= j)])
                break
        hop_record.append({'hop':'down',
                            'jop_date':hop_date,
                            'ex_hop_price':ex_hop_price,
                            'post_hop_price':post_hop_price,
                            'fill_data':fill_data,
                            'fill_day':fill_day })
    hop_df = pd.DataFrame(hop_record)
    # hop_df[hop_df.fill_day <> '']         #已经回补
    # hop_df.fill_day.isnull()  #没有回补
    return hop_df


def compute_condition_up_add_up(df,condition_up):

    if len(condition_up) == 1:
        idx_date = condition_up.jop_date[0]
        idx_close = df.loc[idx_date,'close']
        # df2 = df[df.index >= idx_date]
        # condition_up2 = df2.query(f'high > high.shift(1) and close > close.shift(1)*0.99 and close >= {idx_close}')  #1跳空新高收高
        condition_up2 = df.query(f'low > low.shift(1) and high > high.shift(1) and close > high.shift(1)*0.999 and high > upper')  #2跳空新高收高
        condition_up3 = df.query('(close - close.shift(1))/close.shift(1)*100 > 4 and close >= high*0.99')
        condition_up2 = pd.concat([condition_up2,condition_up3],axis=0)
    elif len(condition_up) > 1:
        # idx_date = condition_up.index[0]
        # idx_close = condition_up.close[0]

        idx_date = condition_up.jop_date[0]
        idx_close = df.loc[idx_date,'close']
        # df2 = df[df.index >= idx_date]
        # condition_up2 = df2.query(f'high > high.shift(1) and close > close.shift(1)*0.99 and close >= {idx_close}')  #1跳空新高收高
        # condition_up2 = df2.query(f'low > low.shift(1) and high > high.shift(1) and close > close.shift(1) and close > {idx_close}')  #2跳空新高收高
        # condition_up2 = df.query(f'low > low.shift(1) and high > high.shift(1) and close > high.shift(1)*0.999')  #2跳空新高收高
        condition_up2 = df.query(f'low > low.shift(1) and high > high.shift(1) and close > high.shift(1)*0.999 and high > upper')  #2跳空新高收高
        condition_up3 = df.query('(close - close.shift(1))/close.shift(1)*100 > 6 and close >= high*0.99')
        
        condition_up2 = pd.concat([condition_up2,condition_up3],axis=0)
    else:
        condition_up2 = pd.DataFrame()
        # condition_up3 = pd.DataFrame()

    return condition_up2

def compute_perd_df(dd,lastdays=3,resample ='d'):
    if resample == 'd':
        last_TopR_days = ct.compute_lastdays
    else:
        # last_TopR_days = 5
        last_TopR_days = ct.compute_lastdays

    np.seterr(divide='ignore',invalid='ignore')  #RuntimeWarning: invalid value encountered in greater
    # df = dd[-(lastdays+1):].copy()

    df = dd.copy()
    # df['max5'] = df['high'].rolling(5).max()
    # df['high4'] = df['high'].rolling(4).max()
    # df['low4'] = df['low'].rolling(4).min()
    # df['hmax'] = df['high'].rolling(10).max()
    # df['lastdu4'] = (df['high'].rolling(4).max()-df['low'].rolling(4).min())/df['low'].rolling(4).min()
    df['max5'] = df.close[-6:-1].max()
    df['max10'] = df.close[-10:-1].max()
    # df['hmax'] = df.high[-6:-1].max()
    df['hmax'] = df.close[-ct.tdx_max_int_end:-ct.tdx_high_da].max()
    # df['hmax60'] = df.high[:-1].max()
    df['high4'] = df.close[-5:-1].max()
    df['low4'] = df.low[-5:-1].min()
    # df['lastdu4'] = (df['high4'][0] -df['low4'][0]) /df['low4'][0]
    df['lastdu4'] = df['high4'][0] /df['low4'][0]

    df['lastupper'] = len(df[(df.close > df.upper) & (df.upper > 0)])
    
    df = df[-(last_TopR_days+1):]
    # df['perlastp'] = list(map(cct.func_compute_percd2021, df['open'], df['close'], df['high'], df['low'],df['open'].shift(1), 
    #                         df['close'].shift(1), df['high'].shift(1), df['low'].shift(1),df['ma5d'],df['ma10d'],df['vol'],df['vol'].shift(1),df['upper'],df.index))

    df['perlastp'] = list(map(cct.func_compute_percd2021, df['open'], df['close'], df['high'], df['low'],df['open'].shift(1), 
                            df['close'].shift(1), df['high'].shift(1), df['low'].shift(1),df['ma5d'],df['ma10d'],df['vol'],df['vol'].shift(1),df['upper'],df.index,df['high4'],df['max5'],df['hmax'],df['lastdu4'],df['code']))
    # df['high4'],df['max5'],df['hmax'],df['lastdu4']
    # df.high[-2:-1].max(),df.high[-3:-1].max(),df.high[-5:-1].max(),df.high[-2:-1].max()/df.low[-2:-1].min()
    #df['high'].rolling(2).max(),df['high'].rolling(3).max(),df['high'].rolling(5).max(),df['high'].rolling(2).max()/df['low'].rolling(2).min()

    df['perlastp'] = df['perlastp'].apply(lambda x: round(x, 2))

    df['perd'] = ((df['close'] - df['close'].shift(1)) / df['close'].shift(1) * 100).map(lambda x: round(x, 1))
    # df['perd'] = ((df['low'] - df['low'].shift(1)) / df['close'].shift(1) * 100).map(lambda x: round(x, 1))
    # df = df.dropna(subset=['perd'])
    # idx_close = df.query('perd == perd.max()')[:1].close
    idx_close_temp = df.query('high > upper')

    idx_close = idx_close_temp.close[0] if len(idx_close_temp) > 0 else df[df.perd == df.perd.max()].close[0]
    idx_date_temp = df.query('high > upper')
    idx_date  = idx_date_temp.index[0] if len(idx_date_temp) > 0 else df[df.high == df.high.max()].index[0]
    # idx_top = df[df.high]
    # red_cout = df.query('(high > high.shift(1) and low > low.shift(1)) or (close > upper and close > low*1.05) or (low >= open*0.992 and close >= open)')

    red_cout = eval(f"df.query('close >={idx_close}  and ((high > high.shift(1) and low > low.shift(1) and close > close.shift(1)) or (close > upper and close > low*1.05) or (low >= open*0.992 and close >= open ))')")
    df2 = df[df.index >= idx_date]
    green_cout = df2.query('(low < low.shift(1) and high < high.shift(1)) or (close < open)')
    
    # df = df.dropna(subset=['perd'])

    # df['red'] = ((df['close'] - df['open']) / df['close'] * 100).map(lambda x: round(x, 1))
    df['lastdu'] = ((df['high'] - df['low']) / df['close'] * 100).map(lambda x: round(x, 1))
    # df['perddu'] = ((df['high'] - df['low']) / df['low'] * 100).map(lambda x: round(x, 1))
    # dd['upperT'] = dd.close[ (dd.upper > 0) & (dd.high > dd.upper)].count()

    # dd['upperT'] = df.close[-10:][ (df.upper > 0) & (df.high > df.upper)].count()
    dfupper=df[-5:]
    
    upperT = dfupper.close[-10:][ (dfupper.upper > 0) & (dfupper.close > dfupper.upper)]
    # dd['upperT'] = df.close[-10:][ (df.upper > 0) & (df.close > df.upper)].apply(lambda x: round(x, 0)).median()
    dd['upperT'] = len(upperT)
    df = df[~df.index.duplicated()]

    # upperL = dd.close[ (dd.upper > 0) & (dd.close >= dd.upper)]

    # upperL = df.close[ (df.close > df.open) & (df.close > df.ene)]
    # upperL = df.close[ (df.high > df.upper) & (df.close > df.ma5d*0.99) ]

    # upperL = df.close[ ((df.high > df.upper) | (df.upper > df.upper.shift(1)) ) & (df.close >= df.ma5d*0.99) ]
    
    upperL = dfupper.close[ (dfupper.high > dfupper.upper) & (dfupper.upper >0) ]


    # upperL = df.close[ (df.high > df.upper) & (df.close > df.ma5d) & (df.close > df.close.shift(1)) ]

    # top_10 = df[df.perd >9.9]
    # if len(top_10) >0:
    #     if len(top_10) == len(df[df.index >= top_10.index[0]]):
    #         top_ten = len(top_10)
    #     else:
    #         top_ten = 0
    # else:
    #     top_ten = 0

    dd['upperL'] = len(upperL) 


    # dd['df2'] = round(df.truer[2:].mean(),1)

    # if len(upperT) > 1:
    #     dd['df2'] = upperT.apply(lambda x: round(x, 0)).median()
    # elif len(upperL) > 0:
    #     dd['df2'] = upperL.apply(lambda x: round(x, 0)).median()
    # else:
    #     dd['df2'] = dd.upper[-5:].apply(lambda x: round(x, 0)).median()
    # df['percent'] =((df.close - df.open)/df.open*100).apply(lambda x:int(x) if x < 10 else 10)  
    # df['percent'] =((df.close - df.close.shift(1))/df.close.shift(1)*100).apply(lambda x:int(x) if x < 30 else 0)
    df['percent'] =((df.close - df.close.shift(1))/df.close.shift(1)*100).apply(lambda x:int(x) if x < 200 else 0)
    # dd['df2'] = df[df.lastdu == df.lastdu.max()].close.values[0]
    dd['percmax'] = df.percent[:-1].max()
    # dd['df2'] = round(df[df.percent == df.percent.max()].close.values[0],1)
    dd['df2'] = round(df[df.percent == df.percent.max()].close.values[0] if len(df.query('high > upper')) == 0 else df.query('high > upper').close[0],1)
    
    df = df.dropna(subset=['perd'])

    # if len(upperT) > 0:
    #     dd['df2'] = len(dd) - dd.index.tolist().index(upperT.index[-1])
    # elif len(upperL) > 0:
    #     dd['df2'] = len(dd) - dd.index.tolist().index(upperL.index[-1])
    # else:
    #     dd['df2'] = dd.upper[-5:].apply(lambda x: round(x, 0)).median()

    # LIS_TDX(df.truer)



    # if len(df.truer) > 0:
    #     cum_maxf, posf = LIS_TDX(df.truer)
    #     if len(df.truer) == len(df[df.index >= upperL.index[0]]):
    #         if len(cum_maxf) == len(upperL):
    #             dd['upperT'] = len(upperL) + top_ten
    #         else:
    #             dd['upperT'] = top_ten
    #     else:
    #         dd['upperT'] = len(cum_maxf) 
    # else:
    #     dd['upperT'] = -1

    # dd['upperT'] = round(df.truer.max(),1)


    # truer_idx = df[df.truer == df.truer.max()].index[0]
    # dd['upperT'] = len(df[df.index <= truer_idx])


    # dd['upperL'] = df.close[df.low > df.upper].count()

    dd['red'] = len(red_cout)
    dd['gren'] = len(green_cout)

    #old ra max
    # ra = round((df.close[-1]-dd.close.max())/df.close[-1]*100,1)
    # if ra == 0.0:
    #     ra = round((df.close[-1]-df.close.min())/df.close[-1]*100,1)
    # dd['ra'] = ra

    # temp_du = df['perd'] - df['lastdu']
    # print df[df.close > df.ma5d]


    # condition_up = df[df['low'] > df['high'].shift()]
    # top0 = df[(df['low'] == df['high']) & (df['low'] <> 0)]

    # # dd['topR']=temp_du.T[temp_du.T >= 0].count()    #跳空缺口
    # # dd['top0']=temp_du.T[temp_du.T == 0].count()    #一字涨停
    # dd['topR'] = condition_up.count()
    # dd['top0'] = top0.count()

    # https://blog.csdn.net/xingbuxing_py/article/details/89323460
    # print(len(dd),dd.code[0])  #fix np.seterr(divide='ignore',invalid='ignore') 

    top15 = dd[-ct.ddtop0:].query('(low >= open*0.992 or open > open.shift(1)) and close > open and ((high > upper or high > high.shift(1)) and close > close.shift(1)*1.04)')
    top0 = dd[-ct.ddtop0:].query('low == high and low != 0')
    # top0 = dd[(dd['low'] == dd['high']) & (dd['low'] != 0)]  #一字涨停


    ''' 旧的跳空未计算回补
    condition_up = dd[dd['low'] > dd['high'].shift()]        #向上跳空缺口
    condition_down = dd[dd['high'] < dd['low'].shift()]      #向下跳空缺口

    # hop_df = compute_condition_up(dd)

    dd['topR'] = len(condition_up)
    dd['topD'] = len(condition_down)
    dd['top0'] = len(top0)

    if len(condition_up) > 0 and len(condition_down) > 0:
        if condition_up.index[-1] > condition_down.index[-1]:
            close_idx_up = condition_up.low[0]
        else:
            close_idx_up = condition_down.high[0]
            dd['topR'] = -len(condition_down)
    else:
        close_idx_up = condition_up.low[0] if len(condition_up) > 0 else dd.close.max()

    '''

    #计算回补
    # last_TopR_days -> 15

    hop_df = compute_condition_up(dd[-15:])
    # condition_up = hop_df[hop_df.hop == 'up']
    condition_up = hop_df[(hop_df.fill_day.isnull() ) & (hop_df.hop == 'up')]   if len(hop_df) > 0  else pd.DataFrame()
    condition_up2 = compute_condition_up_add_up(dd[-15:],hop_df)
    # condition_down = hop_df[hop_df.hop == 'down']
    condition_down = hop_df[ (hop_df.fill_day.isnull() ) & (hop_df.hop == 'down')] if len(hop_df) > 0  else pd.DataFrame()
    # fill_day_up = hop_df[( hop_df.fill_day.notnull() ) & (hop_df.hop == 'up')] if len(hop_df) > 0  else pd.DataFrame()
    # fill_day_down = hop_df[ (hop_df.fill_day.notnull() ) & (hop_df.hop == 'down') ] if len(hop_df) > 0  else pd.DataFrame()

    dd['top0'] = len(top0)
    dd['top15'] = len(top15)

    # if len(fill_day_down) > 0 and len(fill_day_up) > 0:

    # if len(condition_up) >= len(condition_down) :

    if len(condition_up) > 0 :
        dd['topR'] = len(condition_up)+len(condition_up2)-dd.gren.values[-1]
        dd['topD'] = len(condition_down)
    else:
        dd['topR'] = 0
        dd['topD'] = len(condition_down)

    if len(condition_up) > 0 and len(condition_down) > 0:
        if condition_up.jop_date.values[-1] > condition_down.jop_date.values[-1]:
            close_idx_up = dd[dd.index == condition_up.jop_date.values[0]].low[0]
        else:
            close_idx_up = dd[dd.index == condition_down.jop_date.values[0]].high[0]
            dd['topR'] = -len(condition_down)
    else:
        if len(condition_up) > 0:
            close_idx_up = dd[dd.index == condition_up.jop_date.values[0]].low[0] 
            # close_idx_up = dd[dd.index == condition_up.jop_date.values[0]].low[0] if len(condition_up) > 0 else dd.close.max()
        elif len(condition_down) > 0:
            close_idx_up = dd[dd.index == condition_down.jop_date.values[0]].high[0] 
        else:
            close_idx_up = dd.close.min()


    # ra = round((df.close[-1]-dd.close.max())/df.close[-1]*100,1)
    # ra = round((df.close[-1]-close_idx_up)/df.close[-1]*100,1)

    # ra = round((df.close[-1]-close_idx_up)/close_idx_up*100,1)
    #跳空缺口的价差diff

    # ra = round((df.close[-1]-df.close.min())/df.close.min()*100,1)
    
    # ra = round((dd.close[-1]-dd.close.min())/dd.close.min()*100,1)
    # LIS_TDX_Cum(df2.ma5d[:10])


    upper_dd = dd[(dd.upper > 0) & (dd.high > dd.upper)]
    upper_start = upper_dd.high[0] if len(upper_dd) > 0 else dd.high.max()
    if resample == 'd' :
        ral = round((dd.close[-1]-upper_start)/upper_start*100,1)
        # ral = round((dd.close[-1]-dd.high[:-1].max())/dd.high[:-1].max()*100,1)
    else:
        # ral = round((dd.close[-1]-dd.high.max())/dd.high.max()*100,1)
        ral = round((dd.close[-1]-upper_start)/upper_start*100,1)


    df_ma20d=dd[-20:]

    if  resample == 'd':
        ma20d_upper = len(df_ma20d.query('low > ma20d'))
    elif resample == '3d' or resample == 'w':
        ma20d_upper = len(df_ma20d.query('low > ma10d'))
    else:
        ma20d_upper = len(df_ma20d.query('low > ma5d'))


    # if ra == 0.0:
    #     ra = round((df.close[-1]-df.close.min())/dd.close.min()*100,1)

    # dd['ra'] = ra
    # dd['ral'] = ral

    dd['ral'] = ma20d_upper
    
    cum_maxf, posf = LIS_TDX(dd.high[-5:])
    dd['up5'] = len(posf)

    if resample == 'd':
        df['perd'] = df['perd'].apply(lambda x: round(x, 1) if ( x < 9.85)  else 10.0)

    dd['perd'] = df['perd'][~df.index.duplicated()]
    dd.fillna(ct.FILLNA,inplace=True)    #ct.FILLNA -101

    # print dataframe_mode_round(df.high)
    # print dataframe_mode_round(df.low)

    # dd['lastdu'] = df[-4:]['lastdu'].max()
    dd['lastdu'] = df[-ct.tdx_high_da:]['lastdu'].mean()
    dd['perlastp'] = df['perlastp']

    dd = compute_power_tdx_df(df, dd)
    
    return dd

def resample_dataframe_recut(temp,resample='d',increasing=True,check=False):

    ascending=None

    if not temp.index.is_monotonic_increasing:
        log.info(f'increasing is False')
        ascending=False
        temp = temp.sort_index(ascending=True)

    # else:
    #     ascending=False
        
    if resample == 'm':
        temp = temp[-10:]
    elif resample == 'w':
        temp = temp[-30:]
    elif resample == '3d':
        temp = temp[-60:]
    else:
        temp = temp[-90:]

    if ascending is not None:
        temp = temp.sort_index(ascending=ascending)   
    return temp

def compute_upper_cross(dd,ma1='upper',ma2='ma5d',ratio=0.02,resample='d'):    
    df = dd[(dd[ma1] != 0)]
    df = df[-ct.upper_cross_days:]
    # temp = df[ (df[ma1] > df[ma2] * (1-ratio))  & (df[ma1] < df[ma2] * (1+ratio)) ]
    # temp = df[(df.low > df.upper)]
    temp = df[(df.high >= df.upper)]
    # if len(temp) >0 and  temp.index[-1] == df.index[-1]:
    #     dd['topU'] = len(temp)
    # else:
    #     dd['topU'] = 0
    dd['topU'] = len(temp) 
    #high >= df.upper
    dd['eneU'] = len(df[(df.close >= df.ene)])
    #close >= df.ene
    
    return dd


def compute_ma_cross(dd,ma1='ma5d',ma2='ma10d',ratio=0.02,resample='d'):
    #low

    temp = dd
    # temp = df[ (df[ma1] > df[ma2] * (1-ratio))  & (df[ma1] < df[ma2] * (1+ratio)) ]
    # temp = df[ ((df.close > df.ene) & (df.close < df.upper)) & (df[ma1] > df[ma2] * (1-ratio))  & (df[ma1] < df[ma2] * (1+ratio))]
    # temp default: temp.sort_index(ascending=False)

    temp=resample_dataframe_recut(temp,resample=resample)

    if len(temp) > 0:
        temp_close = temp.low
        if len(temp_close[temp_close >0]) >0:
            idx_max = temp.close[:-1].idxmax()
            idx_min = temp_close[:-1].idxmin()
        else:
            idx_min = -1
            idx_max = -1

        if idx_min != -1:
            # fibl = len(dd[dd.index >= idx_min])
            idx = round((dd.close[-1]/temp.close[temp.index == idx_min])*100-100,1)
        else:
            # fibl = -1
            idx = round((dd.close[-1]/temp.close[-1])*100-100,1)
        # if len(temp) == len(df):
        #     fibl = len(dd[dd.index >= temp.index[0]])
        #     idx = round((dd.close[-1]/temp.close[0])*100-100,1)
        # else:
        #     fibl = len(dd[dd.index >= temp.index[-1]])
        #     idx = round((dd.close[-1]/temp.close[-1])*100-100,1)
        dd['op'] = idx
        # dd['fib'] = fibl
        # dd['ra'] = round(idx/fibl,1)
        dd['ldate'] = temp.index[0]
    else:

        temp = dd[ dd[ma1] > dd[ma2]]
        if len(temp) == len(dd) and len(dd) > 0:
            # fibl = len(dd[dd.index >= temp.index[0]])
            idx = round((dd.close[-1]/temp.close[0])*100-100,1)
            dd['op'] = idx
            # dd['fib'] = fibl
            # dd['ra'] = round(idx/fibl,1)
            dd['ldate'] = temp.index[0]
        else:
            idx = 0
            dd['op'] = idx
            dd['fib'] = -1
            # dd['ra'] = -1
            dd['ldate'] = -1
    return dd

def compute_ma_cross_old(dd,ma1='ma5d',ma2='ma10d',ratio=0.02):

    df = dd[(dd[ma2] != 0)]
    # temp = df[ (df[ma1] > df[ma2] * (1-ratio))  & (df[ma1] < df[ma2] * (1+ratio)) ]
    temp = dd[ ((dd.close > dd.ene) & (dd.close < df.upper)) & (dd[ma1] > dd[ma2] * (1-ratio))  & (dd[ma1] < dd[ma2] * (1+ratio))]

    if len(temp) > 0:
        temp_close = temp.close - temp.ene
        if len(temp_close[temp_close >0]) >0:
            idx_min = temp_close.idxmax()
        else:
            idx_min = -1

        if idx_min != -1:
            # fibl = len(dd[dd.index >= idx_min])
            idx = round((dd.close[-1]/temp.close[temp.index == idx_min])*100-100,1)
        else:
            # fibl = -1
            idx = round((dd.close[-1]/temp.close[-1])*100-100,1)
        # if len(temp) == len(df):
        #     fibl = len(dd[dd.index >= temp.index[0]])
        #     idx = round((dd.close[-1]/temp.close[0])*100-100,1)
        # else:
        #     fibl = len(dd[dd.index >= temp.index[-1]])
        #     idx = round((dd.close[-1]/temp.close[-1])*100-100,1)
        dd['op'] = idx
        # dd['fib'] = fibl
        # dd['ra'] = round(idx/fibl,1)
        dd['ldate'] = temp.index[0]
    else:

        temp = dd[ dd[ma1] > dd[ma2]]
        if len(temp) == len(dd) and len(dd) > 0:
            # fibl = len(dd[dd.index >= temp.index[0]])
            idx = round((dd.close[-1]/temp.close[0])*100-100,1)
            dd['op'] = idx
            # dd['fib'] = fibl
            # dd['ra'] = round(idx/fibl,1)
            dd['ldate'] = temp.index[0]
        else:
            idx = 0
            dd['op'] = idx
            dd['fib'] = -1
            # dd['ra'] = -1
            dd['ldate'] = -1
    return dd

def compute_lastdays_percent(df=None, lastdays=3, resample='d',vc_radio=100):
    # ct.compute_lastdays lastdays to 9
    if df is not None and len(df) > lastdays:
        # if cct.get_trade_date_status() == 'True' and resample != 'd' :

        # if resample != 'd' and cct.get_trade_date_status() == 'True':
        #     df = df[:-1]

            # print "df:",df[-1:]
        if len(df) > lastdays + 1:
            # 判断lastdays > 9 
            lastdays = len(df) - 1
            lastdays = lastdays if lastdays < ct.compute_lastdays else ct.compute_lastdays
        else:
            lastdays = len(df) - 1
        if 'date' in df.columns:
            df = df.set_index('date')
        df = df.sort_index(ascending=True)
        if cct.get_work_day_status() and 915 < cct.get_now_time_int() < 1500:
            df = df[df.index < cct.get_today()]
        # df['ma5d'] = pd.Series.rolling(df.close, 5)

#        df['perd'] = ((df['close'] - df['close'].shift(1)) / df['close'].shift(1) * 100).map(lambda x: round(x, 1) if ( x < 9.85)  else 10.0)

        df['ma5d'] = pd.Series.rolling(df.close, 5).mean().apply(lambda x: round(x,2))
        df['ma10d'] = pd.Series.rolling(df.close, 10).mean().apply(lambda x: round(x,2))
        df['ma20d'] = pd.Series.rolling(df.close, 26).mean().apply(lambda x: round(x,2))
        df['ma60d'] = pd.Series.rolling(df.close, 60).mean().apply(lambda x: round(x,2))
        # df['natr'] = ta.natr(df.high, df.low, df.close)
        df['truer'] = ta.true_range(df.high, df.low, df.close)

        if len(df) > 33:
            # df['upper'] = [round((1 + 11.0 / 100) * x, 1) for x in df.ma20d]
            # df['lower'] = [round((1 - 9.0 / 100) * x, 1) for x in df.ma20d]
            # df['ene'] = list(map(lambda x, y: round((x + y) / 2, 1), df.upper, df.lower))
            df[['lower', 'ene', 'upper','bandwidth','bollpect']] = ta.bbands(df['close'], length=20, std=2, ddof=0)

        else:
            df['upper'] = [round((1 + 11.0 / 100) * x, 1) for x in df.ma10d]
            df['lower'] = [round((1 - 9.0 / 100) * x, 1) for x in df.ma10d]
            df['ene'] = list(map(lambda x, y: round((x + y) / 2, 1), df.upper, df.lower))
        df['upper'] = df['upper'].apply(lambda x: round(x,1))   
        df['lower'] = df['lower'].apply(lambda x: round(x,1))   
        df['ene'] =  df['ene'].apply(lambda x: round(x,1))  
        df = df.fillna(0)

        dd = compute_ma_cross(df,resample=resample)
        dd = compute_upper_cross(df,resample=resample)

        df = compute_perd_df(df,lastdays=lastdays,resample=resample)
        df['vchange'] = ((df['vol'] - df['vol'].shift(1)) / df['vol'].shift(1) * 100).map(lambda x: round(x, 1))
        df = df.fillna(0)
        df['vcra'] = len(df[df.vchange > vc_radio])
        # df['ma5vol'] = df.vol[-df.fib[0]]
        # df['ma5vol'] = df.vol[-df.fib[0]]
        df['vcall'] = df['vchange'].max()
        # df['vchange'] = df['vchange'][-1]

        # df['meann'] = ((df['high'] + df['low']) / 2).map(lambda x: round(x, 1))
        df_temp = {}
        # df = df.assign(hop=np.nan)s
        for da in range(1, lastdays + 1, 1):
            # df['lastp%sd' % da] = df['close'].shift(da-1)
            # df['lasto%sd' % da] = df['open'].shift(da-1)
            # df['lasth%sd' % da] = df['high'].shift(da-1)
            # df['lastl%sd' % da] = df['low'].shift(da-1)
            # df['lastv%sd' % da] = df['vol'].shift(da-1)
            if da <=6:
                # df['lastp%sd' % da] = df['close'][-da]
            #     df.loc[:,'lasto%sd' % da] = df['open'][-da]
            #     df.loc[:,'lastl%sd' % da] = df['low'][-da]
            #     # df['lastv%sd' % da] = df['vol'][-da]
            #     df.loc[:,'truer%sd' % da] = df['truer'][-da]

            # # df['truer%sd' % da] = df['truer'][-da]
            # df.loc[:,'lasth%sd' % da] = df['high'][-da]
            # df.loc[:,'lastp%sd' % da] = df['close'][-da]

            # df.loc[:,'lastv%sd' % da] = df['vol'][-da]
            # # df['per%sd' % da] = df['close'].pct_change(da).apply(lambda x:round(x*100,1))
            # # df['per%sd' % da] = df['perd'][-da:].sum()
            # df.loc[:,'per%sd' % da] = df['perd'][-da]
            # df.loc[:,'upper%s' % da] = df['upper'][-da]
            # df.loc[:,'ma5%sd' % da] = df['ma5d'][-da]
            # df.loc[:,'ma20%sd' % da] = df['ma20d'][-da]
            # df.loc[:,'ma60%sd' % da] = df['ma60d'][-da]
            # # df['du%sd' % da] = df['perd'][-da] - df['lastdu'][-da]
            # # df['per%sd' % da] = df['perd'].shift(da-1)
            # df.loc[:,'perc%sd' % da] = df['perlastp'][-da]


                df_temp['lasto%sd' % da] = df['open'][-da]
                df_temp['lastl%sd' % da] = df['low'][-da]
                # df['lastv%sd' % da] = df['vol'][-da]
                df_temp['truer%sd' % da] = df['truer'][-da]

            # df['truer%sd' % da] = df['truer'][-da]
            df_temp['lasth%sd' % da] = df['high'][-da]
            df_temp['lastp%sd' % da] = df['close'][-da]

            df_temp['lastv%sd' % da] = df['vol'][-da]
            # df['per%sd' % da] = df['close'].pct_change(da).apply(lambda x:round(x*100,1))
            # df['per%sd' % da] = df['perd'][-da:].sum()
            df_temp['per%sd' % da] = df['perd'][-da]
            df_temp['upper%s' % da] = df['upper'][-da]
            df_temp['ma5%sd' % da] = df['ma5d'][-da]
            df_temp['ma20%sd' % da] = df['ma20d'][-da]
            df_temp['ma60%sd' % da] = df['ma60d'][-da]
            # df['du%sd' % da] = df['perd'][-da] - df['lastdu'][-da]
            # df['per%sd' % da] = df['perd'].shift(da-1)
            df_temp['perc%sd' % da] = df['perlastp'][-da]

        df_repeat = pd.DataFrame([df_temp]).loc[np.repeat(0, len(df))].reset_index(drop=True)
        df = pd.concat([df.reset_index(), df_repeat], axis=1)
        df = df.set_index('date').sort_index(ascending=True)

        # new_row_df = pd.DataFrame([df_temp]) 
        # df = pd.concat([df, new_row_df], ignore_index=True)
            # df['perc%sd' % da] = (df['perlastp'][-da:].sum())
        # df['lastv9m'] = df['vol'][-lastdays:].mean()
            # df['mean%sd' % da] = df['meann'][-da]

        df = compute_top10_count(df)

        df = compute_ma5d_count(df,madays='5')     #ma5dcum
        # df = compute_ma5d_count(df,madays='20')   #ma20dcum
        # df = compute_ma5d_ra(df,madays='5')   #ma5d ra

        df = df.reset_index()
    else:
        log.info("compute df is none")

    return df


def get_tdx_exp_low_or_high_price(code, dt=None, ptype='close', dl=None, end=None):
    '''
    :param code:999999
    :param dayl:Duration Days
    :param type:TDX type
    :param dt:  Datetime
    :param ptype:low or high
    :return:Series or df
    '''
    # dt = cct.day8_to_day10(dt)
    if dt is not None and dl is not None:
        # log.debug("dt:%s dl:%s"%(dt,dl))
        df = get_tdx_Exp_day_to_df(
            code, start=dt, dl=dl, end=end).sort_index(ascending=False)
        if df is not None and not df.empty:
            if len(str(dt)) == 10:
                dz = df[df.index >= dt]
                # if dz.empty:
                # dd = Series(
                # {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
                # 'vol': 0})
                # return dd
                if len(dz) < abs(int(dl) - changedays):
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                if isinstance(dz, Series):
                    # dz=pd.DataFrame(dz)
                    # dz=dz.set_index('date')
                    return dz

            else:
                if len(df) > int(dl):
                    dz = df[:int(dl)]
                else:
                    dz = df
            if dz is not None and not dz.empty:
                if ptype == 'high':
                    lowp = dz.high.max()
                    lowdate = dz[dz.high == lowp].index.values[-1]
                    log.debug("high:%s" % lowdate)
                elif ptype == 'close':
                    lowp = dz.close.min()
                    lowdate = dz[dz.close == lowp].index.values[-1]
                    log.debug("close:%s" % lowdate)
                else:
                    lowp = dz.low.min()
                    lowdate = dz[dz.low == lowp].index.values[-1]
                    log.debug("low:%s" % lowdate)

                log.debug("date:%s %s:%s" % (lowdate, ptype, lowp))
                # log.debug("date:%s %s:%s" % (dt, ptype, lowp))
                dd = df[df.index == lowdate]
                if len(dd) > 0:
                    dd = dd[:1]
                    dt = dd.index.values[0]
                    dd = dd.T[dt]
                    dd['date'] = dt
            else:
                dd = pd.Series([],dtype='float64')

        else:
            log.warning("code:%s no < dt:NULL" % (code))
            dd = pd.Series([],dtype='float64')
            # dd = Series(
            #     {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
            #      'vol': 0})
        return dd
    else:
        dd = get_tdx_Exp_day_to_df(code, dl=1)
        return dd


def get_tdx_exp_low_or_high_power(code, dt=None, ptype='close', dl=None, end=None, power=False, lastp=False, newdays=None, resample='d', lvoldays=ct.lastdays * 3):
    '''
    :param code:999999
    :param dayl:Duration Days
    :param type:TDX type
    :param dt:  Datetime
    :param ptype:low or high
    :return:Series or df
    '''
    # dt = cct.day8_to_day10(dt)
    
    if dt is not None or dl is not None:
        # log.debug("dt:%s dl:%s"%(dt,dl))
        df = get_tdx_Exp_day_to_df(code, start=dt, dl=dl, end=end, newdays=newdays, resample=resample).sort_index(ascending=False)
        if df is not None and len(df) > 5:
            # if power:
            #     from JSONData import powerCompute as pct
            #     dtype = resample
            #     opc = 0
            #     stl = ''
            #     rac = 0
            #     # fib = []
            #     # sep = '|'
            #     fibl = '0'
            #     fib = '0'
            #     for pty in ['low', 'high']:
            #         op, ra, st, daysData = pct.get_linear_model_status(
            #             code, df=df, dtype=dtype, start=dt, end=end, dl=dl, filter='y', ptype=pty, power=False)
            #         opc += op
            #         rac += ra
            #         if pty == 'low':
            #             stl = st
            #             fibl = str(daysData[0])
            #         else:
            #             fib = str(daysData[0])
            #     df['op'] = opc
            #     df['ra'] = rac
            #     df['fib'] = fib
            #     df['fibl'] = fibl
            #     df['ldate'] = stl

            df=resample_dataframe_recut(df,resample=resample)

            if lastp:
                dd = df[:1]
                dt = dd.index.values[0]
                dd = dd.T[dt]
                dd['date'] = dt
                if 'ma5d' in df.columns and 'ma10d' in df.columns:
                    if df[:1].ma5d[0] is not None and df[:1].ma5d[0] != 0:
                        dd['ma5d'] = round(float(df[:1].ma5d[0]), 2)
                    if df[:1].ma10d[0] is not None and df[:1].ma10d[0] != 0:
                        dd['ma10d'] = round(float(df[:1].ma10d[0]), 2)
                return dd

            if len(str(dt)) == 10:
                dz = df[df.index >= dt]
                # if dz.empty:
                # dd = Series(
                # {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
                # 'vol': 0})
                # return dd
                if len(dz) < abs(int(dl) - changedays):
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                if isinstance(dz, Series):
                    # dz=pd.DataFrame(dz)
                    # dz=dz.set_index('date')
                    return dz

            else:
                if len(df) > int(dl):
                    dz = df[:int(dl)]
                else:
                    dz = df
            if dz is not None and not dz.empty:
                if ptype == 'high':
                    lowp = dz.close.max()
                    lowdate = dz[dz.close == lowp].index.values[-1]
                    # log.debug("high:%s" % lowdate)
                elif ptype == 'close':
                    lowp = dz.close.min()
                    lowdate = dz[dz.close == lowp].index.values[-1]
                    # log.debug("close:%s" % lowdate)
                else:
                    lowp = dz.close.min()
                    lowdate = dz[dz.close == lowp].index.values[-1]
                    # log.debug("low:%s" % lowdate)


                volmean = dz.vol[:lvoldays].tolist()
                
                if len(volmean) > 5:
                    volmean.remove(min(volmean))    
                    volmean.remove(max(volmean))  

                # lastvol = dz.vol[:lvoldays].min()
                lastvol = round(sum(volmean) / len(volmean),1)

                # log.debug("date:%s %s:%s" % (lowdate, ptype, lowp))

                # log.debug("date:%s %s:%s" % (dt, ptype, lowp))
                dtemp = df[df.index == lowdate]
                dd = df[:1]

                # if ptype == 'high':
                #     lowp = dz.low.min()
                #     dd.low = lowp
                # else:
                #     highp = dz.high.max()
                #     dd.high = highp
                    # print dd.high
                if len(dd) > 0:
                    dd = dd[:1]
                    dt = dd.index.values[0]
                    dd = dd.T[dt]
                    dd['date'] = lowdate

                dd['high'] = dtemp.high.values[0]
                dd['low'] = dtemp.low.values[0]
                dd['close'] = dtemp.close.values[0]
                dd['open'] = dtemp.open.values[0]
                # dd['vol'] = 

                dd['lowvol'] = dtemp.vol.values[0]
                #min vol date
                dd['last6vol'] = lastvol

                # if 'ma5d' in df.columns and 'ma10d' in df.columns:
                #     #                    print df[:1],code
                #     if len(df.ma5d) > 0 and df[:1].ma5d.values[0] is not None and df[:1].ma5d.values[0] != 0:
                #         dd['ma5d'] = round(float(df[:1].ma5d.values[0]), 2)
                #     if len(df.ma10d) > 0 and df[:1].ma10d.values[0] is not None and df[:1].ma10d.values[0] != 0:
                #         dd['ma10d'] = round(float(df[:1].ma10d.values[0]), 2)
            else:
                dd = pd.Series([],dtype='float64')

        else:
            log.debug("code:%s no < dt:NULL" % (code))
            # df = get_tdx_append_now_df_api_tofile(code)
            df = get_kdate_data(code, start='', end='', ktype='D',ascending=False)
            if len(df) > 30:
                write_tdx_tushare_to_file(code, df=df, start=None, type='f',rewrite=True)
            dd = pd.Series([],dtype='float64')
            # dd = Series(
            #     {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
            #      'vol': 0})
        return dd
    else:
        dd = get_tdx_Exp_day_to_df(code, dl=1)
        return dd


# def get_tdx_day_to_df_last(code, dayl=1, type=0, dt=None, ptype='close', dl=None, newdays=None):
#     '''
#     :param code:999999
#     :param dayl:Duration Days
#     :param type:TDX type
#     :param dt:  Datetime
#     :param ptype:low or high
#     :return:Series or df
#     '''
#     # dayl=int(dayl)
#     # type=int(type)
#     # print "t:",dayl,"type",type
#     if newdays is not None:
#         newstockdayl = newdays
#     else:
#         newstockdayl = newdaysinit
#     if not type == 0:
#         f = (lambda x: str((1000000 - int(x))) if x.startswith('0') else x)
#         code = f(code)
#     code_u = cct.code_to_symbol(code)
#     day_path = day_dir % 'sh' if code.startswith(
#         ('5', '6', '9')) else day_dir % 'sz'
#     p_day_dir = day_path.replace('/', path_sep).replace('\\', path_sep)
#     # p_exp_dir=exp_dir.replace('/',path_sep).replace('\\',path_sep)
#     # print p_day_dir,p_exp_dir
#     file_path = p_day_dir + code_u + '.day'
#     if not os.path.exists(file_path):
#         ds = Series(
#             {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
#              'vol': 0})
#         return ds
#     ofile = file(file_path, 'rb')
#     b = 0
#     e = 32
#     if dayl == 1 and dt == None:
#         log.debug("%s" % (dayl == 1 and dt == None))
#         fileSize = os.path.getsize(file_path)
#         if fileSize < 32:
#             print "why", code
#         ofile.seek(-e, 2)
#         buf = ofile.read()
#         ofile.close()
#         a = unpack('IIIIIfII', buf[b:e])
#         # if len(a) < 7:
#         #     continue
#         tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
#         topen = float(a[1] / 100.0)
#         thigh = float(a[2] / 100.0)
#         tlow = float(a[3] / 100.0)
#         tclose = float(a[4] / 100.0)
#         amount = float(a[5] / 10.0)
#         tvol = int(a[6])  # int
#         # tpre = int(a[7])  # back
#         dt_list = Series(
#             {'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose, 'amount': amount,
#              'vol': tvol})
#         return dt_list
#     elif dayl == 1 and dt is not None and dl is not None:
#         log.debug("dt:%s" % (dt))
#         dt_list = []
#         # if len(str(dt)) == 8:
#         # dt = cct.day8_to_day10(dt)
#         # else:
#         # dt=get_duration_price_date(code, ptype=ptype, dt=dt)
#         # print ("dt:%s"%dt)
#         fileSize = os.path.getsize(file_path)
#         if fileSize < 32:
#             print "why", code
#         b = fileSize
#         ofile.seek(-fileSize, 2)
#         no = int(fileSize / e)
#         if no < newstockdayl:
#             return pd.Series([],dtype='float64')
#         # print no,b,day_cout,fileSize
#         buf = ofile.read()
#         ofile.close()
#         # print repr(buf)
#         # df=pd.DataFrame()
#         for i in xrange(no):
#             a = unpack('IIIIIfII', buf[-e:b])
#             if len(a) < 7:
#                 continue
#             tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
#             topen = float(a[1] / 100.0)
#             thigh = float(a[2] / 100.0)
#             tlow = float(a[3] / 100.0)
#             tclose = float(a[4] / 100.0)
#             amount = float(a[5] / 10.0)
#             tvol = int(a[6])  # int
#             # tpre = int(a[7])  # back
#             dt_list.append({'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose,
#                             'amount': amount, 'vol': tvol})
#             # print series
#             # dSeries.append(series)
#             # dSeries.append(Series({'code':code,'date':tdate,'open':topen,'high':thigh,'low':tlow,'close':tclose,'amount':amount,'vol':tvol,'pre':tpre}))
#             b = b - 32
#             e = e + 32
#             # print tdate,dt
#             if tdate < dt:
#                 # print "why"
#                 break
#         df = pd.DataFrame(dt_list, columns=ct.TDX_Day_columns)
#         # print "len:%s %s"%(len(df),fileSize)
#         df = df.set_index('date')
#         dt = get_duration_price_date(code, ptype=ptype, dt=dt, df=df, dl=dl)
#         log.debug('last_dt:%s' % dt)
#         dd = df[df.index == dt]
#         if len(dd) > 0:
#             dd = dd[:1]
#             dt = dd.index.values[0]
#             dd = dd.T[dt]
#             dd['date'] = dt
#         else:
#             log.warning("no < dt:NULL")
#             dd = pd.Series([],dtype='float64')
#             # dd = Series(
#             # {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
#             # 'vol': 0})
#         return dd
#     else:
#         dt_list = []
#         fileSize = os.path.getsize(file_path)
#         # print fileSize
#         day_cout = abs(e * int(dayl))
#         # print day_cout
#         if day_cout > fileSize:
#             b = fileSize
#             ofile.seek(-fileSize, 2)
#             no = int(fileSize / e)
#         else:
#             no = int(dayl)
#             b = day_cout
#             ofile.seek(-day_cout, 2)
#         # print no,b,day_cout,fileSize
#         buf = ofile.read()
#         ofile.close()
#         # print repr(buf)
#         # df=pd.DataFrame()
#         for i in xrange(no):
#             a = unpack('IIIIIfII', buf[-e:b])
#             if len(a) < 7:
#                 continue
#             tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
#             topen = float(a[1] / 100.0)
#             thigh = float(a[2] / 100.0)
#             tlow = float(a[3] / 100.0)
#             tclose = float(a[4] / 100.0)
#             amount = float(a[5] / 10.0)
#             tvol = int(a[6])  # int
#             # tpre = int(a[7])  # back
#             dt_list.append({'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose,
#                             'amount': amount, 'vol': tvol})
#             # print series
#             # dSeries.append(series)
#             # dSeries.append(Series({'code':code,'date':tdate,'open':topen,'high':thigh,'low':tlow,'close':tclose,'amount':amount,'vol':tvol,'pre':tpre}))
#             b = b - 32
#             e = e + 32
#         df = pd.DataFrame(dt_list, columns=ct.TDX_Day_columns)
#         df = df.set_index('date')
#         return df


#############################################################
# usage Ê¹ÓÃËµÃ÷
#
#############################################################
def get_tdx_all_day_LastDF(codeList, dt=None, ptype='close'):
    '''
    outdate
    '''
    time_t = time.time()
    # df = rl.get_sina_Market_json(market)
    # code_list = np.array(df.code)
    # if type==0:
    #     results = cct.to_mp_run(get_tdx_day_to_df_last, codeList)
    # else:
    if dt is not None:
        if len(str(dt)) != 8:
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            dl = len(df[df.index >= dt])
            log.info("LastDF:%s" % dt)
        else:
            # dt = int(dt)+10
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            dl = len(df[df.index >= dt])
            log.info("LastDF:%s" % dt)
    else:
        dl = None
    results = cct.to_mp_run_async(
        get_tdx_Exp_day_to_df, codeList, start=None, end=None, dl=1, newdays=0)
    # get_tdx_day_to_df_last, codeList, 1, type, dt, ptype, dl)
    # results=[]
    # for code in codeList:
    # results.append(get_tdx_day_to_df_last(code, 1, type, dt,ptype))


#    df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
    df = pd.DataFrame(results)
    df = df.set_index('code')
    # df.loc[:, 'open':] = df.loc[:, 'open':].astype(float)
    log.info("get_to_mp:%s" % (len(df)))
    log.info("TDXTime:%s" % (time.time() - time_t))
    if dt != None:
        print(("TDX:%0.2f" % (time.time() - time_t)), end=' ')
    return df

def get_single_df_lastp_to_df(top_all, lastpTDX_DF=None, dl=ct.PowerCountdl, end=None, ptype='low', filter='y', power=True, lastp=False, newdays=None, checknew=True, resample='d'):

    time_s = time.time()
    codelist = top_all.index.tolist()
#    codelist = ['603169']
    log.info('toTDXlist:%s dl=%s end=%s ptype=%s' % (len(codelist), dl, end, ptype))
    # print codelist[5]
    h5_fname = 'tdx_last_df'
    # market=ptype+'_'+str(dl)+'_'+filter+'_'+str(len(codelist))
    if end is not None:
        h5_table = ptype + '_' + resample + '_' + str(dl) + '_' + filter + \
            '_' + end.replace('-', '') + '_' + 'all'
    else:
        h5_table = ptype + '_' + resample + '_' + str(dl) + '_' + filter + '_' + 'all'

    # if newdays is not None:
    #     h5_table = h5_table + '_'+ str(newdays)

    log.info('h5_table:%s' % (h5_table))

    # codelist = dm.index.tolist()
    # codelist.extend(tdx_index_code_list)
    # search_Tdx_multi_data_duration(cct.tdx_hd5_name, 'all_300',code_l=codelist, start=60, end=None, index='date')

    if lastpTDX_DF is None or len(lastpTDX_DF) == 0:
        # h5 = top_hdf_api(fname=h5_fname,table=market,df=None)
        h5 = h5a.load_hdf_db(h5_fname, table=h5_table,
                             code_l=codelist, timelimit=False)

        if h5 is not None and not h5.empty:
            #            o_time = h5[h5.time <> 0].time
            #            if len(o_time) > 0:
            #                o_time = o_time[0]
            #            print time.time() - o_time
            #                if time.time() - o_time > h5_limit_time:
            log.info("load hdf data:%s %s %s" % (h5_fname, h5_table, len(h5)))
            tdxdata = h5
        else:
            log.error("TDX None:%s")
            return top_all
    else:
        tdxdata = lastpTDX_DF

    top_all = cct.combine_dataFrame(
        top_all, tdxdata, col=None, compare=None, append=False)

    # log.info('Top-merge_now:%s' % (top_all[:1]))
    top_all = top_all[top_all['llow'] > 0]
    log.debug('T:%0.2f'%(time.time()-time_s))
    return top_all

def compute_jump_du_count(df,lastdays=ct.compute_lastdays,resample='d'):

    # if 'op' in df.columns and 'boll' in df.columns:
    #     df = df[(df.op > -1) & (df.boll > -1)]
    _Integer = int(lastdays/10) 
    _remainder = lastdays%10


    #没有用处理顺序截取非个股处理
    # if _Integer > 0:
    #     # temp=df.loc[:,df.columns.str.contains( "per\d{1,2}d$",regex= True)]
    #     temp=df[df.columns[((df.columns >= 'per1d') & (df.columns <= 'per%sd'%(9)))]]
    #     #lastday > 20 error !!!!
    #     # if _Integer > 1:
    #     #     for i in range(1,_Integer, 1):
    #     #         # temp=df[df.columns[((df.columns >= 'per1d') & (df.columns <= 'per%sd'%(9))) | ((df.columns >= 'per%s0d'%(_Integer)) & (df.columns <= 'per%s%sd'%(_Integer,_remainder))) ]]
    #     #         # d_col=df[ ((df.columns >= 'per%s0d'%(_Integer)) & (df.columns <= 'per%s%sd'%(_Integer,_remainder))) ]
    #     #         d_col=df[df.columns[((df.columns >= 'per%s0d'%(i)) & (df.columns <= 'per%s%sd'%(i,9)))]]
    #     #         temp = cct.combine_dataFrame(temp, d_col, col=None, compare=None, append=False, clean=True)
    #     d_col=df[df.columns[((df.columns >= 'per%s0d'%(_Integer)) & (df.columns <= 'per%s%sd'%(_Integer,_remainder)))]]
    #     temp = cct.combine_dataFrame(temp, d_col, col=None, compare=None, append=False, clean=True)


    # else:

    #     temp=df[df.columns[(df.columns >= 'per1d') & (df.columns <= 'per%sd'%(lastdays))]]
    
    temp=df.loc[:,df.columns.str.contains( "per\d{1,2}d$",regex= True)]

    if resample == 'd':
        tpp =temp[temp >9.9].count()
        # temp[temp >9.9].per1d.dropna(how='all')
        idxkey= tpp[ tpp ==tpp.min()].index.values[0]
        perlist = temp.columns[temp.columns <= idxkey][-2:].values.tolist()
        if len(perlist) >=2:
            # codelist= temp[ ((temp[perlist[0]] >9) &(temp[perlist[1]] > 9)) | (temp[perlist[1]] > 9) ].index.tolist()
            codelist= temp[ ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 9) ].index.tolist()
            # temp[ ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 9) | ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 0)].shape
        else:
            codelist= temp[ (temp[perlist[0]] >9.9)].index.tolist()
    else:
        codelist = temp.index.tolist()
        # tpp =temp[temp >9.9].count()
        # # temp[temp >9.9].per1d.dropna(how='all')
        # idxkey= tpp[ tpp ==tpp.min()].index.values[0]
        # perlist = temp.columns[temp.columns <= idxkey][-2:].values.tolist()
        # if len(perlist) >=2:
        #     # codelist= temp[ ((temp[perlist[0]] >9) &(temp[perlist[1]] > 9)) | (temp[perlist[1]] > 9) ].index.tolist()
        #     codelist= temp[ ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 9) ].index.tolist()
        #     # temp[ ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 9) | ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 0)].shape
        # else:
        #     codelist= temp[ (temp[perlist[0]] >9.9)].index.tolist()


    return codelist

# def compute_ma5d_ra(df,lastdays=ct.compute_lastdays,madays='5'):
#     # temp=df[df.columns[(df.columns >= 'ma%s1d'%(madays)) & (df.columns <= 'ma%s%sd'%(madays,lastdays))]][-1:]
#     temp=df.ma5d[-10:]
#     cum_min,ops=LIS_TDX_Cum(temp.sort_index(ascending=False).values)
#     #倒叙新低了几天
#     # sorted([20.57, 21.35, 22.04, 22.68, 22.92,23.1,23.2,23.4,23.5],reverse=True)
#     df['ra']=ops[-1]+1 if ops[-1] > 0 else 0
#     return df

def compute_ma5d_count(df,lastdays=ct.compute_lastdays,madays='5'):
    # temp=df[df.columns[(df.columns >= 'ma%s1d'%(madays)) & (df.columns <= 'ma%s%sd'%(madays,lastdays))]][-1:]
    # temp=df[df.columns[(df.columns >= 'ma%s1d'%(madays)) & (df.columns <= 'ma%s%sd'%(madays,lastdays))]]

    temp=df.loc[:,df.columns.str.contains( "ma%s\d{1,2}d$"%(madays),regex= True)]

    # temp_du=df[df.columns[(df.columns >= 'du1d') & (df.columns <= 'du%sd'%(lastdays))]]
    # temp.T[temp.T >=10].count()

    df['ma%sdcum'%(madays)]=(temp.T.sum()/lastdays)
    df['ma%sdcum'%(madays)] = df['ma%sdcum'%(madays)].apply(lambda x: round(x,1))  
      
    # df['topU']=temp.T[temp.T >= top_limit].count()  #0.8 上涨个数  compute_upper_cross
    # df['topR']=temp_du.T[temp_du.T >= 0].count()    #跳空缺口
    # df['top0']=temp_du.T[temp_du.T == 0].count()    #一字涨停
    # df['upper'] = map(lambda x: round((1 + 11.0 / 100) * x, 1), df.ma10d)
    # df['lower'] = map(lambda x: round((1 - 9.0 / 100) * x, 1), df.ma10d)
    # df['ene'] = map(lambda x, y: round((x + y) / 2, 1), df.upper, df.lower)
    df = df.fillna(0)
    return df

def compute_top10_count(df,lastdays=ct.compute_lastdays,top_limit=ct.per_redline):
    # top_temp.loc[:,top_temp.columns.str.contains('perc')]
    # top_temp.loc[:,top_temp.columns.str.startswith('perc')]
    # temp.loc[:,temp.columns.str.contains( "per\d{1,2}d$",regex= True)]
    # temp=df.loc[:,df.columns.str.contains( "perc\d{1,2}d$",regex= True)]

    # temp=df[df.columns[(df.columns >= 'per1d') & (df.columns <= 'per%sd'%(lastdays))]][-15:]
    temp=df.loc[:,df.columns.str.contains( "per\d{1,2}d$",regex= True)]
    # temp_du=df[df.columns[(df.columns >= 'du1d') & (df.columns <= 'du%sd'%(lastdays))]]
    # temp.T[temp.T >=10].count()

    df['top10']=temp.T[temp.T >=9.9].count()        #涨停个数

    # df['topU']=temp.T[temp.T >= top_limit].count()  #0.8 上涨个数  compute_upper_cross
    # df['topR']=temp_du.T[temp_du.T >= 0].count()    #跳空缺口
    # df['top0']=temp_du.T[temp_du.T == 0].count()    #一字涨停
    # df['upper'] = map(lambda x: round((1 + 11.0 / 100) * x, 1), df.ma10d)
    # df['lower'] = map(lambda x: round((1 - 9.0 / 100) * x, 1), df.ma10d)
    # df['ene'] = map(lambda x, y: round((x + y) / 2, 1), df.upper, df.lower)
    df = df.fillna(0)
    return df

def get_index_percd(codeList=tdx_index_code_list, dt=60, end=None, ptype='low', filter='n', power=False, lastp=False, newdays=None, dl=None, resample='d', showRunTime=True):
    tdxdata = get_tdx_exp_all_LastDF_DL(codeList, dt=dt, end=end, ptype=ptype, filter=filter, power=power, lastp=lastp, newdays=newdays, resample=resample)
    return tdxdata


def get_append_lastp_to_df(top_all, lastpTDX_DF=None, dl=ct.PowerCountdl, end=None, ptype='low', filter='y', power=True, lastp=False, newdays=None, checknew=True, resample='d',showtable=False):

    codelist = top_all.index.tolist()
    # append INDEX tdxdata
    codelist.extend(tdx_index_code_list)
    codelist = list(set(codelist))
    # tdx_index_data = get_append_lastp_to_df()tdd.get_append_lastp_to_df(
    #                         top_now, lastpTDX_DF=None, dl=duration_date, checknew=True, resample=resample)

#    codelist = ['603169']
    log.info('toTDXlist:%s dl=%s end=%s ptype=%s' % (len(codelist), dl, end, ptype))
    # print codelist[5]
    h5_fname = 'tdx_last_df'
    # market=ptype+'_'+str(dl)+'_'+filter+'_'+str(len(codelist))
    if end is not None:
        h5_table = ptype + '_' + resample + '_' + str(dl) + '_' + filter + \
            '_' + end.replace('-', '') + '_' + 'all'
    else:
        h5_table = ptype + '_' + resample + '_' + str(dl) + '_' + filter + '_' + 'all'

    # if newdays is not None:
    #     h5_table = h5_table + '_'+ str(newdays)

    log.info('h5_table:%s' % (h5_table))

    # codelist = dm.index.tolist()
    # codelist.extend(tdx_index_code_list)
    # search_Tdx_multi_data_duration(cct.tdx_hd5_name, 'all_300',code_l=codelist, start=60, end=None, index='date')
    if lastpTDX_DF is None or len(lastpTDX_DF) == 0:
        # h5 = top_hdf_api(fname=h5_fname,table=market,df=None)
        h5 = h5a.load_hdf_db(h5_fname, table=h5_table,
                             code_l=codelist, timelimit=False,showtable=showtable)

        if h5 is not None and not h5.empty:
            #            o_time = h5[h5.time <> 0].time
            #            if len(o_time) > 0:
            #                o_time = o_time[0]
            #            print time.time() - o_time
            #                if time.time() - o_time > h5_limit_time:
            log.info("load hdf data:%s %s %s" % (h5_fname, h5_table, len(h5)))
            tdxdata = h5
            if cct.GlobalValues().getkey('tdx_Index_Tdxdata') is None:
                #append tdx_Index_Tdxdata
                if tdx_index_code_list[0] in tdxdata.index:
                    cct.GlobalValues().setkey('tdx_Index_Tdxdata', tdxdata.loc[tdx_index_code_list])
        else:
            log.info("no hdf data:%s %s" % (h5_fname, h5_table))
            # tdxdata = get_tdx_all_day_LastDF(codelist) '''only get lastp no
            print(("TDD:%s" % (len(codelist)),))
            
            # import ipdb;ipdb.set_trace()

            tdxdata = get_tdx_exp_all_LastDF_DL(
                codelist, dt=dl, end=end, ptype=ptype, filter=filter, power=power, lastp=lastp, newdays=newdays, resample=resample)
            # if checknew:
            #     tdx_list = tdxdata.index.tolist()
            #     diff_code = list(set(codelist) - set(tdx_list))
            #     diff_code = [ co for co in diff_code if co.startswith(('6','00','30'))]
            #     # tdx_diff = None
            #     if len(diff_code) > 0:
            #         # diff_sina = set(top_all.index.values) - set(diff_code)
            #         log.error("tdx Out:%s code:%s"%(len(diff_code),diff_code[:2]))
            #         log.debug("diff_code:%s"%(diff_code))
            #         tdx_diff = get_tdx_exp_all_LastDF_DL(diff_code,dt=dl,end=end,ptype=ptype,filter=filter,power=power,lastp=lastp,newdays=0)
            #         if tdx_diff is not None and len(tdx_diff) >0:
            #             tdxdata = pd.concat([tdxdata, tdx_diff],axis=0)

            # tdxdata.rename(columns={'close': 'llow'}, inplace=True)
            
            tdxdata.rename(columns={'open': 'lopen'}, inplace=True)
            tdxdata.rename(columns={'high': 'lhigh'}, inplace=True)
            tdxdata.rename(columns={'close': 'lastp'}, inplace=True)
            # tdxdata.rename(columns={'low': 'lastp'}, inplace=True)
            tdxdata.rename(columns={'low': 'llow'}, inplace=True)
            tdxdata.rename(columns={'vol': 'lvol'}, inplace=True)
            tdxdata.rename(columns={'amount': 'lamount'}, inplace=True)
            # tdxdata.rename(columns={'cumin': 'df2'}, inplace=True)

            # # aa=df[df.columns[(df.columns >= 'per1d') & (df.columns <= 'per9d')]]
            # aa.T[aa.T >=10].count()
            # df['top1']=aa.T[aa.T >=10].count()
            # tdxdata = compute_top10_count(tdxdata)
            wcdf = wcd.get_wencai_data(top_all.name)
            wcdf['category'] = wcdf['category'].apply(lambda x:x.replace('\r','').replace('\n',''))
            tdxdata = cct.combine_dataFrame(tdxdata, wcdf.loc[:, ['category']])
            # tdxdata = cct.combine_dataFrame(tdxdata, top_all.loc[:, ['name']])
            if cct.GlobalValues().getkey('tdx_Index_Tdxdata') is None:
                if tdx_index_code_list[0] in tdxdata.index:
                    cct.GlobalValues().setkey('tdx_Index_Tdxdata', tdxdata.loc[tdx_index_code_list])
            h5 = h5a.write_hdf_db(
                h5_fname, tdxdata, table=h5_table, append=True)

        log.debug("TDX Col:%s" % tdxdata.columns.values)
    else:
        tdxdata = lastpTDX_DF
    log.debug("TdxLastP: %s %s" %
              (len(tdxdata), tdxdata.columns.values))

    if checknew:
        tdx_list = tdxdata.index.tolist()
        diff_code = list(set(codelist) - set(tdx_list))
        diff_code = [
            co for co in diff_code if co.startswith(('6', '00', '30'))]
        # tdx_diff = None
        if len(diff_code) > 0:
            log.error("tdx Out:%s code:%s" % (len(diff_code), diff_code[:2]))
            # log.debug("diff_code:%s" % (diff_code[-2]))
            tdx_diff = get_tdx_exp_all_LastDF_DL(
                diff_code, dt=dl, end=end, ptype=ptype, filter=filter, power=power, lastp=lastp, newdays=newdays, resample=resample)
            if tdx_diff is not None and len(tdx_diff) > 0:
                tdx_diff.rename(columns={'open': 'lopen'}, inplace=True)
                tdx_diff.rename(columns={'high': 'lhigh'}, inplace=True)
                tdx_diff.rename(columns={'close': 'lastp'}, inplace=True)
                # tdxdata.rename(columns={'low': 'lastp'}, inplace=True)
                tdx_diff.rename(columns={'low': 'llow'}, inplace=True)
                tdx_diff.rename(columns={'vol': 'lvol'}, inplace=True)
                tdx_diff.rename(columns={'amount': 'lamount'}, inplace=True)
                # tdx_diff.rename(columns={'cumin': 'df2'}, inplace=True)
                # tdx_diff = compute_top10_count(tdx_diff)
                # wcdf = wcd.get_wencai_data(top_all.loc[tdx_diff.index,'name'], 'wencai',days='N')
                wcdf = wcd.get_wencai_data(top_all.name)
                wcdf['category'] = wcdf['category'].apply(lambda x:x.replace('\r','').replace('\n',''))
                tdx_diff = cct.combine_dataFrame(tdx_diff, wcdf.loc[:, ['category']])

                if newdays is None or newdays > 0:
                    h5 = h5a.write_hdf_db(h5_fname, tdx_diff, table=h5_table, append=True)
                tdxdata = pd.concat([tdxdata, tdx_diff], axis=0)

                # tdxdata = cct.combine_dataFrame(tdxdata, top_all.loc[:, ['name']])
                
    top_all = cct.combine_dataFrame(
        top_all, tdxdata, col=None, compare=None, append=False)
    # cct.combine_dataFrame(top_all, tdxdata, col=['b1_v','a1_v'], compare=None, append=False).query('9 <percent < 10.2 ')

    # log.info('Top-merge_now:%s' % (top_all[:1]))

    top_all = top_all[top_all['llow'] > 0]
    #20231110 add today topR
    #20250607 mod today topR
    if cct.get_day_istrade_date():
        if cct.get_trade_date_status() == 'False':
            top_all['topR'] =  list(map(lambda x, y, z: (round(x + 1.1,1) if y >= z else x),top_all.topR, top_all.low, top_all.lasth2d))
        # elif 915 < cct.get_now_time_int() < 1500:
        #     top_all['topR'] =  list(map(lambda x, y, z: (x + 1.1 if y > z else x),top_all.topR, top_all.low, top_all.lasth1d))
        elif cct.get_now_time_int() < 915:
            top_all['topR'] =  list(map(lambda x, y, z: (round(x + 1.1,1) if y >= z else x),top_all.topR, top_all.low, top_all.lasth2d))
        else:
            if (top_all['open'][-1] == top_all['lasto1d'][-1]) and (top_all['open'][0] == top_all['lasto1d'][0]):
                top_all['topR'] =  list(map(lambda x, y, z: (round(x + 1.1,1) if y >= z else x),top_all.topR, top_all.low, top_all.lasth2d))
            else:
                top_all['topR'] =  list(map(lambda x, y, z: (round(x + 1.1,1) if y >= z else x),top_all.topR, top_all.low, top_all.lasth1d))

        if cct.get_work_time_duration():
            top_all['topR'] =  list(map(lambda x, y, z,op,high,close: (x + 1.1 if (y > z or (z < op*0.99 and high > z)) else x),top_all.topR, top_all.low, top_all.lasth1d,top_all.open,top_all.high,top_all.close))
        else:
            if (top_all['open'][-1] == top_all['lasto1d'][-1]) and (top_all['open'][0] == top_all['lasto1d'][0]):
                top_all['topR'] =  list(map(lambda x, y, z,op,high,close: (x + 1.1 if ( (y > z and high > z) or (z < op*0.99 and high > z and close > z)) else x),top_all.topR, top_all.low, top_all.lasth2d,top_all.open,top_all.high,top_all.close))
            else: 
                top_all['topR'] =  list(map(lambda x, y, z,op,high,close: (x + 1.1 if ( (y > z and high > z) or (z < op*0.99 and high > z and close > z))  else x),top_all.topR, top_all.low, top_all.lasth1d,top_all.open,top_all.high,top_all.close))
    
    if 'llastp' not in top_all.columns:
        log.error("why not llastp in topall:%s" % (top_all.columns))

    for col in ['boll','dff','df2','ra','ral','fib','fibl']:
        if col in top_all.columns:
            top_all[col] = top_all[col].astype(int)
    top_all['topR']=top_all['topR'].apply(lambda x:round(x,1))
    # top_all = top_all.fillna(0)         
    # tdxdata = tdxdata.fillna(0)            

    for col in ['boll','dff','df2','ra','ral','fib','fibl']:
        if col in tdxdata.columns:
            tdxdata[col] = tdxdata[col].astype(int)
    top_all = cct.reduce_memory_usage(top_all)       
    if lastpTDX_DF is None:
        tdx_code = [co for co in codelist if co in tdxdata.index]
        tdxdata = tdxdata.loc[tdx_code]
        tdxdata = cct.reduce_memory_usage(tdxdata)
        return top_all, tdxdata
    else:
        return top_all


def get_powerdf_to_all(top_all, powerdf):
    # codelist = top_all.index.tolist()
    # all_t = top_all.reset_index()
    # p_t = powerdf.reset_index()
    # top_dif['buy'] = (map(lambda x, y: y if int(x) == 0 else x, top_dif['buy'].values, top_dif['trade'].values))
    time_s = time.time()
    #     columns_list = ['ra', 'op', 'fib', 'ma5d','ma10d', 'ldate', 'ma20d', 'ma60d', 'oph', \
    #                     'rah', 'fibl', 'boll', 'kdj','macd','rsi', 'ma', 'vstd', 'lvolume', 'category', 'df2']
    # #    columns_list = [col for col in powerdf.columns if col in top_all.columns]
    #     if not 'boll' in top_all.columns:
    #         p_t = powerdf.loc[:,columns_list]
    #         # top_all.drop('column_name', axis=1, inplace=True)
    #         # top_all.drop([''], axis = 1, inplace = True, errors = 'ignore')
    #         top_all_co = top_all.columns
    #         top_all.drop([col for col in top_all_co if col in p_t], axis=1, inplace=True)
    #         top_all = top_all.merge(p_t, left_index=True, right_index=True, how='left')
    #         top_all = top_all.fillna(0)
    #     else:
    #         # p_t = powerdf.loc[:,'ra':'df2']
    #         po_inx = powerdf.index
    #         top_all.drop([inx for inx in powerdf.index  if inx in top_all.index], axis=0, inplace=True)
    #         # p_t = powerdf.iloc[:,57:69]
    #         # 'oph', u'rah', u'fibl', u'boll', u'kdj',u'macd', u'rsi', u'ma', u'vstd', u'lvolume', u'category'
    #         # top_all = top_all.merge(p_t, left_index=True, right_index=True, how='left')
    #         top_all = pd.concat([top_all, powerdf],axis=0)
    #         # top_dd =  cct.combine_dataFrame(top_temp[:10], top_end,append=True, clean=True)
    #         # for symbol in p_t.index:
    #         #     if symbol in top_all.index:
    #         #         # top_all.loc[symbol, 'oph':'category'] = p_t.loc[symbol, 'oph':'category']
    #         #         top_all.loc[symbol, 'ra':'df2'] = p_t.loc[symbol, 'ra':'df2']
    #     if 'time' not in top_all.columns:
    # #        top_all['time'] = cct.get_now_time_int()
    #         top_all['time'] = time.time()
    #     else:
    #         top_all = top_all.fillna(0)
    #         time_t = top_all[top_all.time <> 0].time[0] if len(top_all[top_all.time <> 0]) > 0 else 0
    #         if time.time() - time_t > ct.power_update_time:
    #             top_all['time'] = time.time()
    #     print "Pta:%0.2f"%(time.time()-time_s),
    return top_all


def get_tdx_exp_all_LastDF(codeList, dt=None, end=None, ptype='low', filter='n'):
    time_t = time.time()
    # df = rl.get_sina_Market_json(market)
    # code_list = np.array(df.code)
    # if type==0:
    #     results = cct.to_mp_run(get_tdx_day_to_df_last, codeList)
    # else:
    if dt is not None and filter == 'n':
        if len(str(dt)) < 8:
            dl = int(dt) + changedays
            df = get_tdx_Exp_day_to_df(
                '999999', end=end).sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            log.info("LastDF:%s,%s" % (dt, dl))
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
            df = get_tdx_Exp_day_to_df('999999', end=end).sort_index(ascending=False)
            dl = len(df[df.index >= dt]) + changedays
            dt = df[df.index <= dt].index.values[changedays]
            log.info("LastDF:%s,%s" % (dt, dl))
        results = []
        for code in codeList:
            results.append(get_tdx_exp_low_or_high_price(code, dt, ptype, dl))
    elif dt is not None:
        if len(str(dt)) < 8:
            dl = int(dt)
            df = get_tdx_Exp_day_to_df(
                '999999', end=end).sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[0]
            log.info("LastDF:%s,%s" % (dt, dl))
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
            dl = len(get_tdx_Exp_day_to_df('999999', start=dt,
                                           end=end).sort_index(ascending=False))
            # dl = len(get_kdate_data('sh', start=dt))
            log.info("LastDF:%s,%s" % (dt, dl))
        results = cct.to_mp_run_async(
            get_tdx_exp_low_or_high_price, codeList, dt=dt, ptype=ptype, dl=dl, end=end)
      
        # print dt,ptype,dl,end
        # results=[]
        # for code in codelist:
        #     print(code,)
        #     result=get_tdx_exp_low_or_high_price(code, dt=dt, ptype=ptype, dl=dl, end=end)
        #     results.append(result)

    else:
        results = cct.to_mp_run_async(
            get_tdx_Exp_day_to_df, codeList, type='f', start=None, end=None, dl=None, newdays=1)

        # results=[]
        # for code in codelist:
        #     print(code,)
        #     result=get_tdx_Exp_day_to_df(code, type='f', start=None, end=None, dl=None, newdays=1)
        #     results.append(result)

    # print results
#    df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
    df = pd.DataFrame(results)
    df = df.set_index('code')
    # df.loc[:, 'open':] = df.loc[:, 'open':].astype(float)
    # df.vol = df.vol.apply(lambda x: x / 100)
    log.info("get_to_mp:%s" % (len(df)))
    log.info("TDXTime:%s" % (time.time() - time_t))
    if dt != None:
        print(("DFTDXE:%0.2f" % (time.time() - time_t)), end=' ')
    return df


def get_tdx_exp_all_LastDF_DL(codeList, dt=None, end=None, ptype='low', filter='n', power=False, lastp=False, newdays=None, dl=None, resample='d', showRunTime=True):
    """

    Function: get_tdx_exp_all_LastDF_DL

    Summary: TDX init Day by Mp

    # Examples: InsertHere

    Attributes: 

        @param (codeList):InsertHere

        @param (dt) default=None: InsertHere

        @param (end) default=None: InsertHere

        @param (ptype) default='low': InsertHere

        @param (filter) default='n': InsertHere

        @param (power) default=False: InsertHere

        @param (lastp) default=False: InsertHere

        @param (newdays) default=None: InsertHere

        @param (dl) default=None: InsertHere

        @param (resample) default='d': InsertHere

        @param (showRunTime) default=True: InsertHere

    Returns: InsertHere

    """
    time_t = time.time()
    # df = rl.get_sina_Market_json(market)
    # code_list = np.array(df.code)
    # if type==0:
    #     results = cct.to_mp_run(get_tdx_day_to_df_last, codeList)
    # else:
    end = cct.day8_to_day10(end)
    if dt is not None and filter == 'n':
        if len(str(dt)) < 8:
            dl = int(dt)
            dt = None
            # df = get_tdx_Exp_day_to_df('999999',end=end).sort_index(ascending=False)
            # dt = get_duration_price_date('999999', dt=dt,ptype=ptype,df=df)
            # dt = df[df.index <= dt].index.values[changedays]
            log.info("LastDF:%s,%s" % (dt, dl))
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
                df = get_tdx_Exp_day_to_df(
                    '999999', end=end).sort_index(ascending=False)
                dl = len(df[df.index >= dt])
            elif len(str(dt)) == 10:
                df = get_tdx_Exp_day_to_df(
                    '999999', end=end).sort_index(ascending=False)
                dl = len(df[df.index >= dt])
            else:
                log.warning('dt :%s error dl=60,dt->None' % (dt))
                dl = 30
                dt = None
            log.info("LastDF:%s,%s" % (dt, dl))
        results = cct.to_mp_run_async(
            get_tdx_exp_low_or_high_power, codeList, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample)

        # results = get_tdx_exp_low_or_high_price(codeList[0], dt,ptype,dl)

        # results=[]
        # for code in codeList:
        #    print(code,)
        #    results.append(get_tdx_exp_low_or_high_power(code, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample))
           # results.append(get_tdx_exp_low_or_high_price(code, dt, ptype, dl,end,power,lastp,newdays))
        # results = get_tdx_exp_low_or_high_price(codeList[0], dt,ptype,dl)))

#    elif dt is not None and filter == 'y':
#        results = cct.to_mp_run_async(get_tdx_exp_low_or_high_power, codeList, dt, ptype, dl,end,power,lastp,newdays)
    elif dt is not None:
        if len(str(dt)) < 8:
            dl = int(dt)
#            dt = int(dt)
            # dt = None
            # df = get_tdx_Exp_day_to_df('999999',end=end).sort_index(ascending=False)
            # dt = get_duration_price_date('999999', dt=dt,ptype=ptype,df=df)
            # dt = df[df.index <= dt].index.values[0]
#            dt=get_duration_Index_date('999999',dl=dt)
            log.info("Codelist:%s LastDF:%s,%s" % (len(codeList),dt, dl))
            dt = None
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
                df = get_tdx_Exp_day_to_df(
                    '999999', end=end).sort_index(ascending=False)
                dl = len(df[df.index >= dt])
            elif len(str(dt)) == 10:
                df = get_tdx_Exp_day_to_df(
                    '999999', end=end).sort_index(ascending=False)
                dl = len(df[df.index >= dt])
            else:
                log.warning('dt :%s error dl=60,dt->None' % (dt))
                dl = 30
                dt = None
            log.info("LastDF:%s,%s" % (dt, dl))
        if dl is not None and end is not None:
            dl = dl + cct.get_today_duration(end, cct.get_today())
#            print cct.get_today_duration(end,cct.get_today())

        if len(codeList) > 400:
            
            results = cct.to_mp_run_async(
                get_tdx_exp_low_or_high_power, codeList, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample)
                
                # get_tdx_exp_low_or_high_power, codeList, dt, ptype, dl, end, power, lastp, newdays, resample)
            
            # # codeList = ['300055','002443']
            # results=[]
            # from tqdm import tqdm
            # for inx in tqdm(list(range(len(codeList))),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(codeList),ncols=ct.ncols):
            #     code = codeList[inx]
            #     print(code,)
            #     results.append(get_tdx_exp_low_or_high_power(code, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample))
                
            # results=[]
            # for code in codeList:
            # #    print(code,)
            #    results.append(get_tdx_exp_low_or_high_power(code, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample))

        else:
            results = []
            ts = time.time()
            for code in codeList:
                # print(f'codeList:{len(codeList)}code:{code} :dt')
                results.append(get_tdx_exp_low_or_high_power(code, dt, ptype, dl, end, power, lastp, newdays, resample))
            print("tdxdataT:%s"%(round(time.time()-ts,2)),)
#        print round(time.time()-ts,2),
        # print dt,ptype,dl,end
        # for code in codelist:
        #     print code,
        #     print get_tdx_exp_low_or_high_price('600654', dt, ptype, dl,end)

    else:
        dl = None
        # results = cct.to_mp_run_async(
        #     get_tdx_Exp_day_to_df, codeList, type='f', start=None, end=None, dl=None, newdays=1)
        results=[]
        for code in codeList:
           # print(code)
           results.append(get_tdx_Exp_day_to_df, codeList, type='f', start=None, end=None, dl=None, newdays=1)
    # print results
#    df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
    df = pd.DataFrame(results)
    df = df.dropna(how='all')
    if len(df) > 0 and 'code' in df.columns:
        df = df.set_index('code')
        # df.loc[:, 'open':'amount'] = df.loc[:, 'open':'amount'].astype(float)
    # df.vol = df.vol.apply(lambda x: x / 100)
    log.info("get_to_mp:%s" % (len(df)))
    log.info("TDXTime:%s" % (time.time() - time_t))
    # if power and 'op' in df.columns:
    #     df=df[df.op >10]
    #     df=df[df.ra < 11]
    # print "op:",len(df),
    if showRunTime and dl != None:
        global initTdxdata
        if initTdxdata > 2:
            print("All_OUT:%s " % (initTdxdata), end=' ')
        print(("DLTDXE:%0.2f" % (time.time() - time_t)), end=' ')
    return df


# def get_tdx_all_StockList_DF(code_list, dayl=1, type=0):
#     time_t = time.time()
#     # df = rl.get_sina_Market_json(market)
#     # code_list = np.array(df.code)
#     # log.info('code_list:%s' % len(code_list))
#     results = cct.to_mp_run_async(
#         get_tdx_day_to_df_last, code_list, dayl, type)
#     log.info("get_to_mp_op:%s" % (len(results)))
#     # df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
#     # df = df.set_index('code')
#     # print df[:1]
#     print "t:", time.time() - time_t
#     return results


# def get_tdx_all_day_DayL_DF(market='cyb', dayl=1):
#     time_t = time.time()
#     df = rl.get_sina_Market_json(market)
#     code_list = np.array(df.code)
#     log.info('code_list:%s' % len(code_list))
#     results = cct.to_mp_run_async(get_tdx_day_to_df_last, code_list, dayl)
#     log.info("get_to_mp_op:%s" % (len(results)))
#     # df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
#     # df = df.set_index('code')
#     # print df[:1]

#     # print len(df),df[:1]
#     # print "<2015-08-25",len(df[(df.date< '2015-08-25')])
#     # print "06-25-->8-25'",len(df[(df.date< '2015-08-25')&(df.date >
#     # '2015-06-25')])
#     print "t:", time.time() - time_t
#     return results


def get_tdx_search_day_DF(market='cyb'):
    time_t = time.time()
    df = rl.get_sina_Market_json(market)
    code_list = np.array(df.code)
    log.info('code_list:%s' % len(code_list))
    results = cct.to_mp_run(get_tdx_day_to_df, code_list)
    log.info("get_to_mp_op:%s" % (len(results)))
    # df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
    # df = df.set_index('code')
    # print df[:1]

    # print len(df),df[:1]
    # print "<2015-08-25",len(df[(df.date< '2015-08-25')])
    # print "06-25-->8-25'",len(df[(df.date< '2015-08-25')&(df.date >
    print("t:", time.time() - time_t)
    return results

period_type_dic={'w':'W-FRI','m':'BM'}

def get_tdx_stock_period_to_type_in(df, period_day='W-FRI', periods=5, ncol=None, ratiodays=False):
    """_周期转换周K,月K_

    Returns:
        _type_: _description_
    """
    #快速日期处理
    #https://www.likecs.com/show-204682607.html
    stock_data = df.copy()
    period_type = period_type_dic[period_day.lower()]
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
    period_stock_data['vol'] = stock_data[
        'vol'].resample(period_type).sum()
    if ratiodays:
        period_stock_data['amount'] = period_stock_data['amount'].apply(lambda x: round(x / ratio_d, 1))
        period_stock_data['vol'] = period_stock_data['vol'].apply(lambda x: round(x / ratio_d, 1))
                
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

def get_tdx_stock_period_to_type(stock_data, period_day='w', periods=5, ncol=None):
    """_周期转换周K,月K_

    Returns:
        _type_: _description_
    """


    if period_day.lower() in period_type_dic.keys():

        period_type = period_type_dic[period_day.lower()]
    else:
        period_type = period_day

    indextype = True if stock_data.index.dtype == 'datetime64[ns]' else False
    #
    if 915 < cct.get_now_time_int() < 1500 and cct.get_trade_date_status() == 'True' and  cct.get_work_day_status():
    # if cct.get_work_day_status() and 915 < cct.get_now_time_int() < 1500:
        stock_data = stock_data[stock_data.index < cct.get_today()]
    stock_data['date'] = stock_data.index
    if stock_data.index.name == 'date':
        stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
    elif 'date' in stock_data.columns:
        stock_data = stock_data.set_index('date')
        stock_data = stock_data.sort_index(ascending=True)
        stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
    else:
        log.error("index.name not date,pls check:%s" % (stock_data[:1]))


    period_stock_data = stock_data.resample(period_type).last()
    # ÖÜÊý¾ÝµÄÃ¿ÈÕchangeÁ¬ÐøÏà³Ë
    # period_stock_data['percent']=stock_data['percent'].resample(period_type,how=lambda x:(x+1.0).prod()-1.0)
    # ÖÜÊý¾ÝopenµÈÓÚµÚÒ»ÈÕ
    # print stock_data.index[0],stock_data.index[-1]
    # period_stock_data.index =
    # pd.DatetimeIndex(start=stock_data.index.values[0],end=stock_data.index.values[-1],freq='BM')

    period_stock_data['open'] = stock_data[
        'open'].resample(period_type).first()
        # 'open'].resample(period_type).last()
    # ÖÜhighµÈÓÚMax high
    period_stock_data['high'] = stock_data[
        'high'].resample(period_type).max()
    period_stock_data['low'] = stock_data[
        'low'].resample(period_type).min()
    # volumeµÈÓÚËùÓÐÊý¾ÝºÍ
    if ncol is not None:
        for co in ncol:
            period_stock_data[co] = stock_data[co].resample(period_type).sum()
    else:
        period_stock_data['amount'] = stock_data[
            'amount'].resample(period_type).sum()
        period_stock_data['vol'] = stock_data[
            'vol'].resample(period_type).sum()
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
    

    # if period_day.lower() in period_type_dic.keys() and not indextype and period_stock_data.index.name == 'date' and 'date' in period_stock_data.columns:
    if not indextype and period_stock_data.index.name == 'date' and 'date' in period_stock_data.columns:
        # stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
        # period_stock_data = period_stock_data.set_index('date')

        period_stock_data.index = period_stock_data.date
        period_stock_data = period_stock_data.drop(['date'], axis=1)
        # period_stock_data.index = [str(x)[:10] for x in period_stock_data.date]
        # period_stock_data.index.name = 'date'
    else:
        if 'date' in period_stock_data.columns:
            # period_stock_data = period_stock_data.set_index('date')
            # period_stock_data.index = period_stock_data.date
            period_stock_data = period_stock_data.drop(['date'], axis=1)

    # print period_stock_data
    return period_stock_data


'''
def usage(p=None):
    import timeit
#     print """
# for example :
# python %s 999999 20070101 20070302
# python %s -t txt 999999 20070101 20070302
#     """ % (p, p, p)
    status = None
    run = 1
    df = rl.get_sina_Market_json('cyb')
    df = df.set_index('code')
    codelist = df.index.tolist()
    duration_date = 20160101
    ptype = 'low'
    dt = duration_date
    # codeList='999999'
    print("")
    for x in range(1):
        if len(str(dt)) != 8:
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            log.info("LastDF:%s" % dt)
        else:
            dt = int(dt) + changedays
        # print dt
        # top_now = rl.get_market_price_sina_dd_realTime(df, vol, vtype)
        # get_tdx_exp_all_LastDF_DL(codelist,dt=duration_date,ptype=ptype)
        split_t = timeit.timeit(lambda: get_tdx_exp_all_LastDF_DL(
            codelist, dt=duration_date, ptype=ptype), number=run)
        # split_t = timeit.timeit(lambda : get_tdx_all_day_LastDF(codelist,dt=duration_date,ptype=ptype), number=run)
        # split_t = timeit.timeit(lambda: get_tdx_day_to_df_last(codeList, 1, type, dt,ptype),number=run)
        print(("df Read:", split_t))

        dt = duration_date
        if len(str(dt)) != 8:
            dl = int(dt) + changedays
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            log.info("LastDF:%s" % dt)
        else:
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dl = len(get_tdx_Exp_day_to_df('999999', start=dt)) + changedays
            dt = cct.day8_to_day10(dt)

        # print dt,dl
        # strip_tx = timeit.timeit(lambda: get_tdx_exp_low_or_high_price(codeList, dt, ptype, dl), number=run)
        strip_tx = timeit.timeit(lambda: get_tdx_exp_all_LastDF_DL(
            codelist, dt=duration_date, ptype=ptype), number=run)
        # strip_tx = timeit.timeit(lambda : get_tdx_exp_all_LastDF(codelist, dt=duration_date, ptype=ptype), number=run)
        print(("ex Read:", strip_tx))
'''

def write_to_all():
    st = cct.cct_raw_input("will to Write Y or N:")
    if str(st) == 'y':
        Write_market_all_day_mp('all')
    else:
        print("not write")


def python_resample(qs, xs, rands):
    n = qs.shape[0]
    lookup = np.cumsum(qs)
    results = np.empty(n)

    for j in range(n):
        for i in range(n):
            if rands[j] < lookup[i]:
                results[j] = xs[i]
                break
    return results

    # import timeit
    # n = 100
    # xs = np.arange(n, dtype=np.float64)
    # qs = np.array([1.0 / n, ] * n)
    # rands = np.random.rand(n)
    # from numba.decorators import autojit
    # print(timeit.timeit(lambda: python_resample(qs, xs, rands), number=number))
    # # print timeit.timeit(lambda:cct.run_numba(python_resample(qs, xs,
    # # rands)),number=number)
    # print(timeit.timeit(lambda: autojit(lambda: python_resample(qs, xs, rands)), number=number))
    # # print timeit.timeit(lambda:cct.run_numba(python_resample(qs, xs,
    # # rands)),number=number)

def tdx_profile_test():
    resample = 'd'
    code='000002'
    dl=60
    time_s=time.time()
    for i in range(10):
        df = get_tdx_exp_low_or_high_power(code, dl=dl, end=None, ptype='low', power=False, resample=resample)
        # print("time:%s"%( round((time.time()-time_s),2) ))
    print("done")
    # gui_test.py
if __name__ == '__main__':
    # import sys
    # import timeit
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
    # log_level = LoggerFactory.DEBUG
    log.setLevel(log_level)
    # time_s=time.time()
    # check_tdx_Exp_day_duration('all')
    # print("use time:%s"%(time.time()-time_s))
    # import ipdb;ipdb.set_trace()
    write_to_all()
    # code='399001'
    # code='000862'
    # code='000859'
    # code='002870'
    # code='603000'
    # code='002387'
    # code='603888'
    # code='000686'
    # code='600776'
    # code='000837'
    # code='000750'
    # code='000752'
    # print write_tdx_tushare_to_file('300055')
    # print write_tdx_sina_data_to_file('300055')
    '''
    import ipdb;ipdb.set_trace()
    # df=search_Tdx_multi_data_duration()
    #test Jupyter bug
    code_list = sina_data.Sina().market('all').index.tolist()
    df=search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', df=None,code_l=code_list, start='20150501', end=None, freq=None, col=None, index='date')
    code_uniquelist=df.index.get_level_values('code').unique()
    code_select = code_uniquelist[random.randint(0,len(code_uniquelist)-1)]
    round(time.time()-time_s,2),df.index.get_level_values('code').unique().shape,code_select,df.loc[code_select][:2]
    df = df.drop_duplicates()
    '''

    # Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300, rewrite=True)
    # import ipdb;ipdb.set_trace()
    
    # code='603603'
    # df=get_tdx_append_now_df_api_tofile(code)
    # import ipdb;ipdb.set_trace()
    
    code='001896' #豫能控股
    code='002594' #byd
    code='601628' #中国人寿
    code='601015' #陕西黑猫
    code='000988' #华工科技
    code='300346' #南大光电
    code='600499' #科达制造
    code='600438' #隆基绿能
    code='300798' #如意集团
    # code='002828'  
    # code='002176' #江特电机
    code='601127'  #捷荣技术
    code='002620'  #捷荣技术
    code='600240'  #捷荣技术
    # code='300290'  #捷荣技术
    # code='300826'  #测绘股份
    # code='002251'  #步步高
    # code='002512'  #达华智能

    # get_index_percd()

    # wri_index = cct.cct_raw_input("If append  Index 399001... data to tdx[y|n]:")
    # if wri_index == 'y':
    #     for inx in tdx_index_code_list:
    #         get_tdx_append_now_df_api_tofile(inx)

    # code='688106' #科创信息
    # code='399001'
    code = '002238'
    code = '002786'
    code = '002460'
    code = '603887'
    # code = '600240'
    # code = '600890'
    # code = '002865'

    '''

    Date              Open        High         Low       Close   Volume
    2010-01-04   38.660000   39.299999   38.509998   39.279999  1293400   
    2010-01-05   39.389999   39.520000   39.029999   39.430000  1261400   
    2010-01-06   39.549999   40.700001   39.020000   40.250000  1879800   
    2010-01-07   40.090000   40.349998   39.910000   40.090000   836400   
    2010-01-08   40.139999   40.310001   39.720001   40.290001   654600   
    2010-01-11   40.209999   40.520000   40.040001   40.290001   963600   
    2010-01-12   40.160000   40.340000   39.279999   39.980000  1012800   
    2010-01-13   39.930000   40.669998   39.709999   40.560001  1773400   
    2010-01-14   40.490002   40.970001   40.189999   40.520000  1240600   
    2010-01-15   40.570000   40.939999   40.099998   40.450001  1244200 
    df = pd.read_clipboard(parse_dates=['Date'], index_col=['Date'])
    logic = {'Open'  : 'first',
             'High'  : 'max',
             'Low'   : 'min',
             'Close' : 'last',
             'Volume': 'sum'}

    dfw = df.resample('W').apply(logic)
    # set the index to the beginning of the week
    dfw.index = dfw.index - pd.tseries.frequencies.to_offset("6D")
    '''
    
    # dd=pd.read_clipboard(parse_dates=['Date'], index_col=['Date'])

    # df2 = get_tdx_Exp_day_to_df(code,dl=10, end='20221116', newdays=0, resample='d')
    # df = get_tdx_Exp_day_to_df(code, dl=1)
    # 
    # dm = get_sina_data_df(code)
    # df2 = get_tdx_Exp_day_to_df(code,dl=60, end=None, newdays=0, resample='d')

    # df2 = get_tdx_Exp_day_to_df(code,dl=60, end='20230925', newdays=0, resample='d')

    # df = get_tdx_Exp_day_to_df(code,dl=200, end=None, newdays=0, resample='w')
    # df = get_tdx_Exp_day_to_df(code,dl=200, end=None, newdays=0, resample='3d')

    # df = get_tdx_Exp_day_to_df(code,dl=60, start='20230925',end=None, newdays=0, resample='d')
    #get_tdx_exp_all_LastDF_DL() get_tdx_exp_low_or_high_power
    code='600602'
    code='603038'
    code='833171'
    code='688652'
    code='301260'
    code='603518'
    code='002082'
    code='002250'
    code='300084'
    # code='837748'
    # code='920799'
    code='002268'
    # code='603212'
    code='002670'
    code='600110'
    code='001236'
    code_l=['301287', '603091', '605167']
    # df = get_kdate_data(code,ascending=True)
    
    # df = get_tdx_append_now_df_api_tofile(code)
    
    # start = cct.last_tddate(120)
    # dtype = 'w'
    # df=get_tdx_append_now_df_api(code, start=start, end=None).sort_index(ascending=True)
    # print(f'check col is Null:{cct.select_dataFrame_isNull(df[-10:])}')
    # df2 = get_tdx_stock_period_to_type(df, dtype).sort_index(ascending=True)
    # dd = get_tdx_Exp_day_to_df(code,dl=ct.duration_date_day,resample='d')
    # print(f'ral:{dd.ral}')
    # import ipdb;ipdb.set_trace()

    # # dd = compute_ma_cross(dd,resample='d')
    # print(get_tdx_stock_period_to_type(dd)[-5:])
    df = get_tdx_append_now_df_api_tofile('001236')
    # df = get_tdx_append_now_df_api('001236')

    # df2 = get_tdx_exp_low_or_high_power(code,dl=ct.duration_date_day,resample='d' )
    df2 = get_tdx_exp_low_or_high_power(code,dl=ct.duration_date_up,resample='3d' )
    # df2 = get_tdx_exp_low_or_high_power(code,dl=ct.duration_date_month,resample='m' )
    # df2 = get_tdx_exp_low_or_high_power(code,dl=ct.duration_date_week,resample='w' )
    # df2 = get_tdx_exp_low_or_high_power(code,dl=ct.duration_date_day,resample='3d' )
    print(f'df2.maxp: {df2.maxp} maxpcout: {df2.maxpcout}')
    print(f'ldate:{df2.ldate[:2]}')
    df = df2.to_frame().T
    print(df.loc[:,df.columns[df.columns.str.contains('perc')]][-1:])
    print(df.loc[:,df.columns[df.columns.str.contains('per[0-9]{1}d', regex=True, case=False)]][-1:])
    print(f'macdlast1:{df2.macdlast1} macdlast2:{df2.macdlast2} macdlast6:{df2.macdlast6} macddif:{df2.macddif} macddea:{df2.macddea}')
    import ipdb;ipdb.set_trace()
    # write_to_all()
    

    # df2 = get_tdx_exp_low_or_high_power(code,dl=ct.duration_date_day,resample='d' )

    # tmp_df = get_kdate_data(code, start='', end='', ktype='D')
    # if len(tmp_df) > 0:
    #     write_tdx_tushare_to_file(code, df=tmp_df, start=None, type='f')

    # df = get_tdx_append_now_df_api_tofile('301287')
    df=get_tdx_exp_all_LastDF_DL(code_l, dt='80',filter='y', resample='d')
    print(df[:2])
    # code='600005'
    # df2 = get_tdx_exp_low_or_high_power(code,dl=120,resample='d' )
    # df = get_tdx_Exp_day_to_df(code,dl=60, start=None,end=None, newdays=0, resample='d')
    df = get_tdx_Exp_day_to_df(code,dl=ct.duration_date_month, start=None,end=None, newdays=0, resample='m')

    # import ipdb;ipdb.set_trace()

    # df3 = get_tdx_exp_low_or_high_power(code,dl=60)
    # print(df3.macd)
    # df1 = get_tdx_Exp_day_to_df(code,dl=60, start=None,end=None, newdays=0, resample='d').sort_index(ascending=True)
    # diff, dea, macd3 = custom_macd(df1.close)

    # df = get_tdx_power_now_df(code,dl=60, start=None,end=None).sort_index(ascending=True)
    # macd = df.ta.macd(fast=12,slow=26,signal=9)
    # import ipdb;ipdb.set_trace()

    # print(df.loc[:,df.columns[df.columns.str.contains('perc')]][:1].T)
    # df[(df.close > df.upper) & (df.upper > 0) ]
    # import ipdb;ipdb.set_trace()

    # df = get_tdx_Exp_day_to_df(code,dl=60, end='2023-10-13', newdays=0, resample='d')
    df = get_tdx_Exp_day_to_df(code,dl=60, end=None, newdays=0, resample='d')
    # df2 = get_tdx_append_now_df_api_tofile(code)
    print("code:%s boll:%s df2:%s"%(code,df.boll[0],df.df2[0]))

    resample = 'w'
    df = get_tdx_Exp_day_to_df(code,dl=180, end=None, newdays=0, resample=resample,lastdays=3)
    print("code:%s boll:%s df2:%s"%(code,df.boll[0],df.df2[0]))
    # import ipdb;ipdb.set_trace()

    # df2 = get_tdx_Exp_day_to_df(code,dl=134, end=None, newdays=0, resample=resample,lastdays=1)

    # get_tdx_Exp_day_to_df(code, start=None, end=None, dl=None, newdays=None, type='f', wds=True, lastdays=3, resample='d', MultiIndex=False)
    # df3 = compute_jump_du_count(df2, lastdays=9, resample='d')

    # df = get_tdx_exp_low_or_high_power(code, dl=30, newdays=0, resample=resample)
    # df3 =  get_tdx_exp_all_LastDF_DL([code],  dt=60, ptype='low', filter='y', power=ct.lastPower, resample=resample)

    # df3 = get_tdx_append_now_df_api_tofile(code,newdays=0, start=None, end=None, type='f', df=None, dl=10, power=False)

    # type D:\MacTools\WinTools\new_tdx\T0002\export\forwardp\SH688020.txt


    # Write_market_all_day_mp('all')


    # print df2.shape,df2.cumin
    # print get_kdate_data('000859', start='2023-01-01', end='', ktype='D')
    # write_tdx_tushare_to_file(code)
   
    # df = get_tdx_Exp_day_to_df(code, dl=ct.PowerCountdl,end=None, newdays=0, resample='d')
    # print df.perc1d[-1:],df.perc2d[-1:],df.perc3d[-1:],df.perc4d[-1:],df.perc5d[-1:]
    # print df[df.columns[(df.columns >= 'perc1d') & (df.columns <= 'perc%sd'%(9))]][:1]

    # df3 = df.sort_index(ascending=True)
    # print "cumin:",df[:2].cumin.values,df[:2].cumaxe.values,df[:2].cumins.values,df[:2].cumine.values,df[:2].cumaxc.values, df[:2].cmean.values

    # df2 = get_tdx_Exp_day_to_df(code,dl=60, end=None, newdays=0, resample='d')
    # # df4 = df2.sort_index(ascending=True)
    # print "cumin:",df2[:2].cumin.values,df2[:2].cumaxe.values,df2[:2].cumins.values,df2[:2].cumine.values,df2[:2].cumaxc.values, df2[:2].cmean.values

    # print get_tdx_day_to_df_last('999999', type=1)
    # sys.exit(0)
    # log.setLevel(LoggerFactory.INFO)
    # print Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300)
    # print Write_tdx_all_to_hdf(tdx_index_code_list, h5_fname='tdx_all_df', h5_table='all', dl=300,index=True)
    # print Write_sina_to_tdx(tdx_index_code_list,index=True)
    # print cct.get_ramdisk_path('tdx')

    # code_list = sina_data.Sina().market('cyb').index.tolist()
    # code_list.extend(tdx_index_code_list)
    time_s = time.time()


    # df = h5a.load_hdf_db('tdx_all_df_300', table='all_300', timelimit=False,MultiIndex=True)
    # if cct.GlobalValues().getkey(cct.tdx_hd5_name) is None:
    #     # cct.GlobalValues()
    #     cct.GlobalValues().setkey(cct.tdx_hd5_name, df)
    # else:
    #     print "load cct.GlobalValues().setkey('tdx_multi_data') is ok"
    # print df.info()


    # print "t0:%0.2f" % (time.time() - time_s)
    # start = '20170126'
    # start = None
    # time_s = time.time()
    # df = search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', df=None, code_l=code_list, start=start, end=None, freq=None, col=None, index='date')
    # if df is not None:
    #     print "t1:%0.2f %s" % (time.time() - time_s, df.loc['399005'][:2])
    # time_s = time.time()
    # df = search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', code_l=code_list, start=start, end=None, freq=None, col=None, index='date')
    # print "t1:%0.2f" % (time.time() - time_s)
    # if df is not None:
    #     print "1:", df[-1:]




        # print df[df.index.get_level_values('code')]
    # testnumba(1000)
    # n = 100
    # xs = np.arange(n, dtype=np.float64)
    # qs = np.array([1.0/n,]*n)
    # rands = np.random.rand(n)
    # print python_resample(qs, xs, rands)

#    code='300174'
    # dm = get_sina_data_df(sina_data.Sina().market('all').index.tolist())
    # dm = None
    # get_tdx_append_now_df_api_tofile('000838', dm=dm,newdays=0, start=None, end=None, type='f', df=None, dl=10, power=True)
    # get_tdx_append_now_df_api_tofile('002196', dm=dm,newdays=1,dl=5)
#
    # code = '300661'
    # code = '600581'
    # code = '300609'
    # code = '000916'
    # code = '000593'
    code = '000557'
    code = '002175'
    # code = '300707'
    # resample = '3d'
    resample = 'd'
    # code = '000001'
    # code = '000916'
    # code = '600619'

    df = get_tdx_exp_all_LastDF_DL([code],end='2023-10-13',  dt=60, ptype='low', filter='y', power=ct.lastPower, resample=resample)

    # df = get_tdx_exp_low_or_high_power(code, dl=30, newdays=0, resample='d')
    df = get_tdx_Exp_day_to_df(code, dl=60, newdays=0, resample=resample)

    print("day_to_df:", df[:1][['per1d','per2d','per3d']])

    # col_co = df.columns.tolist()
    # col_ra_op = col_co.extend([ 'ra', 'op', 'fib', 'ma5d', 'ma10d', 'ldate', 'hmax', 'lmin', 'cmean'])
    # print col_ra_op,col_co
    # df = df.loc[:,col_ra_op]
    # print get_tdx_exp_low_or_high_power(code, dl=20,end='2017-06-28',ptype='high')
    # print get_tdx_exp_low_or_high_power(code, dl=20, end='2017-06-28', ptype='low')

    # print get_tdx_exp_low_or_high_power(code, dl=60, end=None, ptype='high', power=False, resample=resample)[:1]
    # df = get_tdx_exp_low_or_high_power(code, dl=60, end=None, ptype='low', power=False, resample=resample)
    # print get_tdx_Exp_day_to_df(code, dl=60, newdays=0, resample='m')[:2]
    # print get_tdx_Exp_day_to_df(code, dl=30, newdays=0, resample='d')[:2]
    # print get_tdx_append_now_df_api(code, start=None, end=None, type='f', df=None, dm=None, dl=6, power=True, newdays=0, write_tushare=False).T
    # print get_tdx_append_now_df_api_tofile(code, dm=None, newdays=0, start=None, end=None, type='f', df=None, dl=2, power=True)
    # print df
    # sys.exit(0)
#    print write_tdx_tushare_to_file(code)

    while 1:
        market = cct.cct_raw_input("1Day-Today check Duration Single write all TDXdata append [all,sh,sz,cyb,alla,q,n] :")
        if market != 'q' and market != 'n'  and len(market) != 0:
            if market in ['all', 'sh', 'sz', 'cyb', 'alla']:
                if market != 'all':
                    Write_market_all_day_mp(market, rewrite=True)
                    break
                else:
                    Write_market_all_day_mp(market)
                    break
            else:
                print("market is None ")
        else:
            break

    hdf5_wri_append = cct.cct_raw_input("1Day-Today No check Duration Single write Multi-300 append sina to Tdx data to Multi hdf_300[y|n]:")
    if hdf5_wri_append == 'y':
        for inx in tdx_index_code_list:
            get_tdx_append_now_df_api_tofile(inx)
        print("Index Wri ok 300", end=' ')
        Write_sina_to_tdx(tdx_index_code_list, index=True)
        Write_sina_to_tdx(market='all')
        # print("Index Wri ok 900", end=' ')
        # Write_sina_to_tdx(tdx_index_code_list, index=True,dl=900)
        # Write_sina_to_tdx(market='all', h5_fname='tdx_all_df', h5_table='all', dl=900)
        # Write_sina_to_tdx(market='all', h5_fname='tdx_all_df', h5_table='all', dl=300)


    hdf5_wri = cct.cct_raw_input("Multi-300 write all Tdx data to Multi hdf_300[rw|y|n]:")
    if hdf5_wri == 'rw':
        Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300, rewrite=True)
    elif hdf5_wri == 'y':
        Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300)


    hdf5_wri = cct.cct_raw_input("Multi-900 write all Tdx data to Multi hdf_900[rw|y|n]:")
    if hdf5_wri == 'rw':
        Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=900, rewrite=True)
    elif hdf5_wri == 'y':
        Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=900)

    # hdf5_wri = cct.cct_raw_input("write all index tdx data to hdf[y|n]:")
    # if hdf5_wri == 'y':
        # Write_tdx_all_to_hdf(tdx_index_code_list, h5_fname='tdx_all_df', h5_table='all', dl=300,index=True)
        # Write_tdx_all_to_hdf(market='all')
        # Write_sina_to_tdx(market='all')

        # time_s = time.time()

        # st.close()



    # print get_tdx_Exp_day_to_df('300546',dl=20)
    # print get_tdx_Exp_day_to_df('999999',end=None).sort_index(ascending=False).shape
    # print sina_data.Sina().get_stock_code_data('300006').set_index('code')
#    dd=rl.get_sina_Market_json('cyb').set_index('code')
#    codelist= dd.index.tolist()
#    df = get_tdx_exp_all_LastDF(codelist, dt=30,end=20160401, ptype='high', filter='y')
    # print write_tdx_sina_data_to_file('300583')
    # print get_tdx_Exp_day_to_df('300583',dl=2,newdays=1)

    # write_to_all()
#    print get_tdx_append_now_df_api('600760')[:3]
    # print get_tdx_append_now_df_api('000411')[:3]
    # print get_tdx_Exp_day_to_df('300311',dl=2)[:2]
    # usage()

    # print get_tdx_append_now_df_api_tofile('300583')
    sys.exit(0)
#    print getSinaAlldf('cx')
#    get_append_lastp_to_df(None,end='2017-03-20',ptype='high')
#    print get_tdx_exp_low_or_high_power('603169',dl=10,ptype='high')
    print(get_tdx_exp_low_or_high_power('603169', None, 'high', 14, '2017-03-20', True, True, None))


#    get_tdx_exp_low_or_high_power, codeList, dt, ptype, dl,end,power,lastp,newdays
#    code=['603878','300575']
#    dm = get_sina_data_df(code)
#    code='603878'


#    print get_tdx_append_now_df_api2('603878',dl=2,dm=dm,newdays=5)
#    print write_tdx_sina_data_to_file('999999',dm)
    code = '999999'
#    print get_sina_data_df(code).index
#    print get_tdx_Exp_day_to_df(code,dl=2)
#    print df.date
    sys.exit(0)

    # print get_tdx_append_now_df_api(code,dl=30)
    # ldatedf = get_tdx_Exp_day_to_df(code,dl=1)
    # lastd = ldatedf.date
    # today = cct.get_today()
    # duration = cct.get_today_duration(lastd)
    # print cct.last_tddate(1)
    # print lastd,duration,today
#    300035,300047,300039

    # print get_tdx_append_now_df_api(code,dl=30)[:2]
#    print df
#    print write_tdx_tushare_to_file(code,None)
    sys.exit(0)
#
    df = get_tdx_exp_all_LastDF_DL(
        codeList=codelist, dt=30, end=None, ptype='low', filter='y', power=True)
    # print df[:1]
    sys.exit(0)
    #
    # print get_tdx_write_now_file_api('999999', type='f')
    time_s = time.time()
    print(get_tdx_exp_all_LastDF_DL(codeList=['000034', '300290', '300116', '300319', '300375', '300519'], dt='2016101', end='2016-06-23', ptype='low', filter='n', power=True))
    print("T1:", round(time.time() - time_s, 2))
    time_s = time.time()
    print(get_tdx_exp_all_LastDF_DL(codeList=['300102', '300290', '300116', '300319', '300375', '300519'], dt='2016101', end='2016-06-23', ptype='high', filter='n', power=True))
    print("T2:", round(time.time() - time_s, 2))

    sys.exit(0)
    print("index_Date:", get_duration_Index_date('999999', dl=3))
    print(get_duration_price_date('999999', dl=30, ptype='low', filter=False, power=True))
    print(get_duration_price_date('399006', dl=30, ptype='high', filter=False, power=True))
    # print get_duration_price_date('999999', dl=30, ptype='high',
    # filter=False,power=True)
    sys.exit(0)
    # print get_duration_price_date('999999',ptype='high',dt='2015-01-01')
    # print get_duration_price_date('999999',ptype='low',dt='2015-01-01')
    # df = get_tdx_Exp_day_to_df('300311')
    # print get_tdx_stock_period_to_type(df)
    # print get_sina_data_df(['601998','000503'])
    df = get_tdx_power_now_df(
        '000001', start='20160329', end='20160401', type='f', df=None, dm=None)
    print("a", (df))
    print("b", get_tdx_exp_low_or_high_price('999999', dt='20160101', end='20160401', ptype='low', dl=5))
    sys.exit(0)
    # df = get_tdx_exp_all_LastDF(['600000', '603377', '601998', '002504'], dt=20160301,end=20160401, ptype='low', filter='y')
    # list=['000001','399001','399006','399005']
    # df = get_tdx_all_day_LastDF(list,type=1)
    # print df
    '''
    index_d,dl=get_duration_Index_date(dt='20160101')
    print index_d
    get_duration_price_date('000935',ptype='low',dt=index_d)
    df= get_tdx_append_now_df('99999').sort_index(ascending=True)
    print df[-2:]
    '''
    '''
    # df = get_tdx_exp_low_or_high_price('600000', dt='20160304')
    # df,inx = get_duration_price_date('600000',dt='20160301',filter=False)
    df = get_tdx_append_now_df_api('300502',start='2016-03-03')
    # df= get_tdx_append_now_df_api('999999',start='2016-02-01',end='2016-02-27')
    print "a:%s"%df
    # print df[df.index == '2015-02-27']
    # print df[-2:]
    '''
    time_s = time.time()
    # df = get_tdx_Exp_day_to_df('999999')
    # dd = get_tdx_stock_period_to_type(df)
    # df = get_tdx_exp_all_LastDF( ['999999', '603377','603377'], dt=30,ptype='high')
    # df = get_tdx_exp_all_LastDF(['600000', '603377', '601998', '002504'], dt=20160329,end=None, ptype='low', filter='y')
    # print df
    sys.exit(0)
    # tdxdata = get_tdx_all_day_LastDF(['999999', '603377','603377'], dt=30,ptype='high')
    # print get_tdx_Exp_day_to_df('999999').sort_index(ascending=False)[:1]

    # tdxdata = get_tdx_exp_all_LastDF(['999999', '601998', '300499'], dt=20120101, ptype='high')

    print(get_tdx_exp_low_or_high_price('600610', dl=30))
    # main_test()
    sys.exit()

    # df = get_tdx_day_to_df_last('999999', dt=30,ptype='high')
    # print df
    # df = get_tdx_exp_low_or_high_price('603377', dt=20160101)
    # print len(df), df
    tdxdata = get_tdx_all_day_LastDF(['999999', '601998'])
    # print tdxdata
    # sys.exit(0)

    tdxdata = get_tdx_exp_all_LastDF(['600610', '603377', '000503'], dt=30)
    # tdxdata = get_tdx_all_day_LastDF(['999999','601998'],dt=30)
    print(tdxdata)

    # dt=get_duration_price_date('999999')
    # print dt

    print("t:", time.time() - time_s)
    # df.sort_index(ascending=True,inplace=True)
    # df.index=df.index.apply(lambda x:datetime.time)

    # df.index = pd.to_datetime(df.index)
    # dd = get_tdx_stock_period_to_type(df)
    # print "t:",time.time()-time_s
    # print len(dd)
    # print dd[-1:]

    # df= get_tdx_all_StockList_DF(list,1,1)
    # print df[:6]

    sys.exit(0)
    time_t = time.time()
    # df = get_tdx_allday_lastDF()
    # print "date<2015-08-25:",len(df[(df.date< '2015-08-25')])
    # df= df[(df.date< '2015-08-25')&(df.date > '2015-06-25')]
    # print "2015-08-25-2015-06-25",len(df)
    # print df[:1]
    # print (time.time() - time_t)

    # import sys
    # sys.exit(0)

    # df = rl.get_sina_Market_json('all')
    # code_list = np.array(df.code)
    # print len(code_list)

    # results = cct.to_mp_run_op(get_tdx_day_to_df_last,code_list,2)
    # df=pd.DataFrame((x.get() for x in results),columns=ct.TDX_Day_columns)
    # print df[:1]

    # get_tdx_allday_lastDF()

    # results=cct.to_mp_run(get_tdx_day_to_df,code_list)
    # print results[:2]
    # print len(results)
    # df = rl.get_sina_Market_json('all')
    # print(len(df))
    # code_list = np.array(df.code)
    # get_tdx_all_day_LastDF(code_list)
    # get_tdx_all_day_DayL_DF('all')
    # time.sleep(5)
    # print len(df)
    # df=df.drop_duplicates()
    # print(len(df))
    # for x in df.index:
    #     print df[df.index==x]
    # df=get_tdx_all_day_DayL_DF('all',20)
    # print len(df)
    # dd=pd.DataFrame()
    # for res in df:
    #     print res.get()[:1]
    #     # dd.concat
    #     pass
    # for x in results:
    # print x[:1]
    # df=pd.DataFrame(results,columns=ct.TDX_Day_columns)
    # print df[:1]
    # for res in results:
    #     print res.get()
    # df=pd.DataFrame(results,)
    # for x in  results:
    #     print x
    # for code in results:
    #     print code[:2]
    #     print type(code)
    #     break
    print((time.time() - time_t))

    # print code_list
    # df=get_tdx_day_to_df('002399')
    # print df[-1:]

    # print df[:1]
    # df=get_tdx_day_totxt('002399')
    # print df[:1]
    #
    # df=get_tdx_day_to_df('000001')
    # print df[:1]
    #
    # df=get_tdx_day_totxt('000001')
    # print df[:1]
    #
    # df=get_tdx_day_to_df('600018')
    # df=get_tdx_day_totxt('600018')
    #
    # import tushare as ts
    # print len(df),df[:1]

    # print df[df.]
    # code_stop=[]
    # for code in results:
    #     dt=code.values()[0]
    #     if dt[-1:].index.values < '2015-08-25':
    #         code_stop.append(code.keys())
    # print "stop:",len(code_stop)
    # pprint.pprint(df)

    """
    python readtdxlc5.py 999999 20070101 20070131

    argv = sys.argv[1:]
    try:
        opts, args = getopt.getopt(argv, "ht:", ["help", "type="])
    except getopt.GetoptError:
        usage(sys.argv[0])
        sys.exit(0)
    l_type = 'zip'  # default type is zipfiles!
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage(sys.argv[0])
            sys.exit(1)
        elif opt in ("-t", "--type"):
            l_type = arg
    if len(args) < 1:
        print 'You must specified the stock No.!'
        usage(sys.argv[0])
        sys.exit(1)
    """
