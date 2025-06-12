 # -*- coding:utf-8 -*-
 #
import sys
import pandas as pd
from JSONData import powerCompute as pct
from JSONData import LineHistogram as lht
from JSONData import wencaiData as wcd
from JSONData import get_macd_kdj_rsi as getab
from JSONData import tdx_data_Day as tdd
from JSONData import stockFilter as stf
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct
from JohnsonUtil import LoggerFactory as LoggerFactory
log = LoggerFactory.log
import warnings
warnings.filterwarnings("ignore",".*GUI is implemented.*")

import argparse
def parseArgmain():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('code', type=str, nargs='?', help='999999')
        parser.add_argument('start', nargs='?', type=str, help='20150612')
        parser.add_argument('end', nargs='?', type=str, help='20160101')
        parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['d', 'w', 'm','3d','2d'], default='w',help='DateType')
        parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['f', 'b'], default='f',help='Price Forward or back')
        parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['high', 'low', 'close'], default='low',help='price type')
        parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='y',help='find duration low')
        parser.add_argument('-l', action="store", dest="dl", type=int, default=ct.linePowerCountdl,help='dl default=%s'%(ct.linePowerCountdl))
        parser.add_argument('-s', action="store", dest="days", type=int, default=ct.Power_last_da,help='lastdays')
        parser.add_argument('-m', action="store", dest="mpl", type=str, default='y',help='mpl show')
        parser.add_argument('-i', action="store", dest="line", type=str, choices=['y', 'n'], default='y', help='LineHis show')
        parser.add_argument('-w', action="store", dest="wencai", type=str, choices=['y', 'n'], default='y',help='WenCai Search')
        parser.add_argument('-n', action="store", dest="num", type=int, default=10,help='WenCai Show Num')
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
    run = 1
    strip_tx = timeit.timeit(lambda: get_linear_model_status(
        code, start=start, type=type, filter=filter), number=run)
    print(("ex Read:", strip_tx))


from threading import Thread
class MyThread(Thread):
    def __init__(self, func, args):
        super(MyThread, self).__init__()
        self.func = func
        self.args = args

    def run(self):
        self.result = self.func(*self.args)

    def get_result(self):
        try:
            return self.result
        except Exception:
            return None


# _sum = 0
# def cal_sum(begin, end):
#     # global _sum
#     _sum = 0
#     for i in range(begin, end + 1):
#         _sum += i
#     return  _sum

# """重新定义带返回值的线程类"""

# if __name__ == '__main__':
#     t1 = MyThread(cal_sum, args=(1, 5))
#     t2 = MyThread(cal_sum, args=(6, 10))
#     t1.start()
#     t2.start()
#     t1.join()
#     t2.join()
#     res1 = t1.get_result()
#     res2 = t2.get_result()
#     print(res1 + res2)
def search_ths_data(code):
    fpath = r'./JohnsonUtil\wencai\同花顺板块行业.xls'.replace('\\',cct.get_os_path_sep())
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

def show_ths_data(df):
    # fpath = r'../JohnsonUtil\wencai\同花顺板块行业.xls'
    # df = pd.read_excel(fpath)
    # df = df.reset_index().set_index('股票代码')
    # df['股票代码'] = df['股票代码'].apply(lambda x:cct.symbol_to_code(x.replace('.','')))
    # df = df.set_index('股票代码')
    # df = df.iloc[:,[1,2,4,5,6,7,8,9]]

    if '最新涨跌幅' in df.columns:
        df['最新涨跌幅'] = df['最新涨跌幅'].apply(lambda x:str(round(float(x),2)))
    for col in df.columns:
        if df[col].dtype == 'float64':
            df[col] = df[col].apply(lambda x: (round((x),2)))
    range_count= len(df.columns) if len(df.columns) < 7 else 7

    # '股票简称', '最新价', '最新涨跌幅','首次涨停时间[20250603]' 0,1,2,4 ,7,8,11,13,15'连续涨停天数','涨停原因类别','停封单量占成交量比'
    # '停封单量占成交量比','涨停开板次数'
    # ['股票简称', '最新价', '最新涨跌幅', '涨停[20250603]', '首次涨停时间[20250603]', '最终涨停时间[20250603]', 
    # '涨停明细数据[20250603]', '连续涨停天数[20250603]', '涨停原因类别[20250603]', '涨停封单量[20250603]', '涨停封单额[20250603]',
    # '涨停封单量占成交量比[20250603]', '涨停封单量占流通a股比[20250603]', '涨停开板次数[20250603]', # 'a股市值(不含限售股)[20250603]', 
    # '几天几板[20250603]', '涨停类型[20250603]', 'market_code', 'code']

    columns_str = ''.join(x for x in df.columns)
    if columns_str.find('停封单量占成交量比') > 0:
        df = df.iloc[:,[0,1,2,4 ,7,8,11,13,15]]
    else:
        df = df.iloc[:,[x for x in range(range_count-1)]]

    if f'涨停封单量' in df.columns:
        df[f'涨停封单量'] = df[f'涨停封单量'].apply(lambda x: (round(float(x)/10000,1)))
    df.columns=df.columns.str.replace('涨停封单量占成交量比','封单占比')
    df.columns=df.columns.str.replace('涨停开板次数','开板')
    df.columns=df.columns.str.replace('连续涨停天数','连涨')
    # return (df[df.index == cct.code_to_symbol_ths(code)])
    data = df
    # table, widths=cct.format_for_print(data, widths=True)
    # table=cct.format_for_print2(data).get_string(header=False)
    table =cct.format_for_print(data,header=True)
    # table =cct.format_for_print(data,header=False)
    return table


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
    # print pct.get_linear_model_status('601519', filter='y', dl=34, ptype='low', days=1)
    # sys.exit()
    import re
    if cct.isMac():
        cct.set_console(145, 19)
    else:
        cct.set_console(145, 19)
    parser = parseArgmain()
    parser.print_help()
    # if cct.get_os_system().find('win') >= 0:
    #     import win_unicode_console
    #     win_unicode_console.disable()
    dd = pd.DataFrame()
    while 1:
        try:
            # log.setLevel(LoggerFactory.INFO)
            # log.setLevel(LoggerFactory.DEBUG)
            code = input("code:")
            if len(code) == 0:
                # code='最近两周振幅大于10,日K收盘价大于5日线,今日涨幅排序'
                # code='周线2连阳,最近三周振幅大于10,日K收盘价大于5日线,今日涨幅排序'
                code='日K,4连阳以上,4天涨幅排序,今天阳线'
                code=['上周周线阳,最近三周振幅大于10,日K收盘价大于5日线,今日涨幅排序',\
                    '最近3日内两天日线最高价大于boll上轨,连续两天最低价大于5日线,大于boll上轨天数排序,涨停股以封单除以流通股排序',\
                    '月线收盘价大于20月线,最近3周内有周线收盘价大于boll上轨,连续两周最低价大于5周线,周线低点大于前一周,大于boll上轨天数排序',\
                    '最近三日内最低价大于250日线,最近三日内放量上涨,三日内涨幅排序',\
                    '日K,3连阳以上,3天涨幅排序,收盘价大于boll上轨',\
                    '日K,3连阳以上,最高价大于30天前区间最高价,连续阳线天数排序倒叙']
                for idx in range(len(code)):
                    print("%s: %s"%(idx+1,code[idx]))
                # code='最近三日内最低价大于250日线,最近3日内涨停过,涨停股以当天封单除以流通股排序价's
                code='今日涨停股票'
                print('run:%s'%(code))
            args = parser.parse_args(code.split())
            # if not code.lower() == 'q' and not code.lower() == 'quit' and not code.lower() == 'exit' and not code == 'q' and not code == 'e' and not str(args.code) == 'None' and (args.wencai == 'y' or re.match('[a-zA-Z]+',code) is not None  or re.match('[ \u4e00 -\u9fa5]+',code) == None ):
            # if not cct.get_os_system() == 'mac':
            #     import ipdb;ipdb.set_trace()
            re_words = re.compile(u"[\u4e00-\u9fa5]+")
            if not code.lower() == 'q' and not code.lower() == 'quit' and not code.lower() == 'exit' and not code == 'q' and not code == 'e' \
                and not str(args.code) == 'None' and (args.wencai == 'y' and ( len(re.findall(re_words, code)) >0  )  ):
                # and not str(args.code) == 'None' and (args.wencai == 'y' and ( (re.match(r"[\u4e00-\u9fa5]+",code) is not None or re.match(r"[\u4e00-\u9fa5]+",code[1:]) is not None or re.match(r"[\u4e00-\u9fa5]+",code[2:]) is not None or re.match(r"[\u4e00-\u9fa5]+",code[-2:]) is not None) ) ):
                # and not str(args.code) == 'None' and (args.wencai == 'y' and (re.match('[a-zA-Z]+',code) is  None  and (re.match(r"[\u4e00-\u9fa5]+",code) is not None or re.match(r"[\u4e00-\u9fa5]+",code[1:]) is not None or re.match(r"[\u4e00-\u9fa5]+",code[2:]) is not None or re.match(r"[\u4e00-\u9fa5]+",code[-2:]) is not None) ) ):
                # df  = wcd.get_wencai_Market_url(code,200,pct=False)
                import pywencai
                import datetime
                # df  = pywencai.get(query=code.split()[0], sort_order='asc')
                df  = pywencai.get(query=code.split()[0])
                if not isinstance(df, pd.DataFrame):
                    print("pls run update: pip install -U --no-deps pywencai")
                    print("df is not ok:%s"%(df))
                else:    
                    # if  len(df.columns) == 19:
                    #     df['股票代码'] = df['股票代码'].apply(lambda x:cct.symbol_to_code(x.replace('.','')))
                    #     df = df[ df.股票代码.str.startswith(('30','60','00')) ]

                    #     df = df.set_index('股票代码')

                    #     # df = df.iloc[:,[0,1,2,3,4,5]]
                    #     current_date = datetime.date.today()
                    #     # 获取当前年份
                    #     current_year = current_date.year
                    #     # 获取上一年的日期
                    #     previous_year_date = current_date.replace(year=current_year - 1)
                    #     # 获取上一年的年份
                    #     previous_year = previous_year_date.year
                    #     df.columns=df.columns.str.replace('区间涨跌幅:前复权','')
                    #     df.columns=df.columns.str.replace(str(previous_year),'')
                    #     df.columns=df.columns.str.replace(str(current_year),'')
                    #     # df.iloc[:,[0,1,2,3,4,5,6]]
                    #     if '概念资讯' in df.columns:
                    #         df.drop(['概念资讯'],axis=1,inplace=True)

                    # else:
                        # df = df[ ~ df.股票代码.str.startswith(('688','87','83')) ]
                    df['股票代码'] = df['股票代码'].apply(lambda x:cct.symbol_to_code(x.replace('.','')))
                    df = df[ df.股票代码.str.startswith(('30','60','00')) ]

                    df = df.set_index('股票代码')

                    # df = df.iloc[:,[0,1,2,3,4,5]]
                    current_date = datetime.date.today()
                    # 获取当前年份
                    current_year = current_date.year
                    # 获取上一年的日期
                    previous_year_date = current_date.replace(year=current_year - 1)
                    # 获取上一年的年份
                    previous_year = previous_year_date.year
                    df.columns=df.columns.str.replace('区间涨跌幅:前复权','')
                    df.columns=df.columns.str.replace(str(previous_year),'')
                    df.columns=df.columns.str.replace(str(current_year),'')
                    # df.iloc[:,[0,1,2,3,4,5,6]]
                    if '概念资讯' in df.columns:
                        df.drop(['概念资讯'],axis=1,inplace=True)
                    # print(df.shape,df.columns)
                    
                    dd=df.copy()

                    # columns_strNew = ''.join(x for x in df.columns).replace(']','').replace('[','')
                    def replace_date(df):
                        df.columns=df.columns.str.replace(f'-','')
                        df.columns=df.columns.str.replace(f'[','')
                        df.columns=df.columns.str.replace(f']','')
                        columns_strNew = ''.join(x for x in df.columns)
                        date_list = list(set(re.findall(r'\d+',columns_strNew)))
                        # date_now = re.findall(r'\[\d+\]',columns_strNew)[0])
                        for date_now in date_list:
                            df.columns=df.columns.str.replace(f'{date_now}','')
                        return df,date_list
        
                    df,date_list = replace_date(df)
                    # print(df.shape,df.iloc[:8,[0,1,2,3,4,5]])
                    # if len(df.columns) > 7:
                    #     # print(show_ths_data(df.iloc[:args.num,[0,1,2,3,4,5,6,7]]))
                    #     print(show_ths_data(df.iloc[:20,[0,1,2,3,4,5,6,7]]))
                    # else:
                    #     # print(show_ths_data(df.iloc[:args.num,[x for x in range(len(df.columns)-1)]]))
                    # print(show_ths_data(df.iloc[:20,[x for x in range(len(df.columns)-1)]]))
                    print(show_ths_data(df.iloc[:,[x for x in range(len(df.columns)-1)]]))
                    print(f'Count:{df.shape} and Date:{date_list}')
                    if '涨停原因类别' in df.columns:
                        cct.counterCategory(df,'涨停原因类别')

                    if len(df) == 1:
                        if re.match('[ \\u4e00 -\\u9fa5]+',code) == None:
                            args.code = df.code.values[0]
                        start = cct.day8_to_day10(args.start)
                        end = cct.day8_to_day10(args.end)
                        args.filter = 'y'
                        for ptype in ['low', 'high']:
                            op, ra, st, days = pct.get_linear_model_status(args.code,df=None, dtype=args.dtype, start=start, end=end,
                                                                       days=args.days, ptype=ptype, filter=args.filter,
                                                                       dl=args.dl)
                            # print "%s op:%s ra:%s days:%s  start:%s" % (args.code, op, str(ra), str(days[0]), st)
                            print("op:%s ra:%s days:%s  start:%s" % (op, str(ra), str(days[0]), st))


            elif len(str(args.code)) == 6:

                if args.start is not None and len(args.start) <= 4:
                    args.dl = int(args.start)
                    args.start = None
                
                if args.dtype in ['m']:
                    args.dl = ct.duration_date_month * 2
                elif args.dtype in ['w']:
                    args.dl = ct.duration_date_week

                start = cct.day8_to_day10(args.start)
                end = cct.day8_to_day10(args.end)
                df = None
                print('ths:')
                print((search_ths_data(args.code)))
                if args.line == 'y' and args.mpl == 'y':
                    code = args.code
                    args.filter = 'n'
                    df=lht.get_linear_model_histogramDouble(code, dtype=args.dtype, start=start, end=end,filter=args.filter, dl=args.dl)
                    # args: code, ptype='low', dtype='d', start=None, end=None, vtype='f', filter='n', df=None,dl=None
                    

                    # t1 = MyThread(lht.get_linear_model_histogramDouble, args=(code,'low', args.dtype, start, end,'f',args.filter,None, args.dl))
                    # t1.start()
                    # t1.join()
                    # df = t1.get_result()
                    # candlestick_powercompute(code,start, end)

                    # op, ra, st, days = pct.get_linear_model_status(code,df=df, start=start, end=end, filter=args.filter)
                    # print "%s op:%s ra:%s  start:%s" % (code, op, ra, st)
                    # print "op:%s ra:%s  start:%s" % (op, ra, st)


                    args.filter = 'y'
                    for ptype in ['low', 'high']:
                        op, ra, st, days = pct.get_linear_model_status(args.code,df=df, dtype=args.dtype, start=start, end=end,
                                                                   days=args.days, ptype=ptype, filter=args.filter,
                                                                   dl=args.dl)
                        # print "%s op:%s ra:%s days:%s  start:%s" % (args.code, op, str(ra), str(days[0]), st)
                        print("op:%s ra:%s days:%s  start:%s" % (op, str(ra), str(days[0]), st))
                        if ptype == 'low':
                            ral = ra
                            opl = op
                            stl = st
                            fibl = int(days[0])
                        else:
                            oph = op
                            rah = ra
                            fib = int(days[0])
                            ra = ral


                    # p=multiprocessing.Process(target=get_linear_model_histogramDouble,args=(code, args.ptype, args.dtype, start, end,args.vtype,args.filter,))
                    # p.daemon = True
                    # p.start()
                    # p.join()
                    # time.sleep(6)
                    # num_input = ''
                # else:
                #     code = args.code
                #     if len(code) == 6:
                #         start = cct.day8_to_day10(args.start)
                #         end = cct.day8_to_day10(args.end)
                #         get_linear_model_histogramDouble(code, args.ptype, args.dtype, start, end, args.vtype)
                #         # get_linear_model_histogramDouble(code, args.ptype, args.dtype, start, end, args.vtype)
                #         # candlestick_powercompute(code,start, end)
                #         op, ra, st, days = pct.get_linear_model_status(code, start=start, end=end, filter=args.filter)
                #         print "code:%s op:%s ra:%s  start:%s" % (code, op, ra, st)
                
                if args.mpl == 'y':
                    # from multiprocessing import Process
                    # p = Process(target=pct.get_linear_model_candles, args=(args.code,args.ptype,args.dtype, start, end,args.filter,df,args.dl,args.days,))
                    #   # (args.code,args.ptype,args.dtype, start, end,args.filter,df,args.dl,args.days)
                    # p.start()
                    # p.join()
                    pct.get_linear_model_candles(args.code, dtype=args.dtype, start=start, end=end, ptype=args.ptype,
                                             filter=args.filter,df=df,dl=args.dl,days=args.days)
                else:
                    args.filter = 'y'
                    for ptype in ['low', 'high']:
                        op, ra, st, days = pct.get_linear_model_status(args.code,df=df, dtype=args.dtype, start=start, end=end,
                                                                   days=args.days, ptype=ptype, filter=args.filter,
                                                                   dl=args.dl)
                        # print "%s op:%s ra:%s days:%s  start:%s" % (args.code, op, str(ra), str(days[0]), st)
                        print("op:%s ra:%s days:%s  start:%s" % (op, str(ra), str(days[0]), st))
                        if ptype == 'low':
                            ral = ra
                            opl = op
                            stl = st
                            fibl = (days[0])
                        else:
                            oph = op
                            rah = ra
                            fib = (days[0])
                            ra = ral
                        # op, ra, st, days = get_linear_model_status(args.code, dtype=args.dtype, start=cct.day8_to_day10(
                        # args.start), end=cct.day8_to_day10(args.end), filter=args.filter, dl=args.dl)
                # print "code:%s op:%s ra/days:%s  start:%s" % (code, op, str(ra) + '/' + str(days), st)
                # 'ra * fibl + rah*(abs(int(%s)-fibl))/fib +ma +kdj+rsi'
                boll,kdj,macd,rsi,ma,bollCT = getab.get_All_Count(args.code,dl=args.dl,start=start, end=end,days=ct.Power_Ma_Days,lastday=args.days)
                # print ""
                # print "ral,opl,fibl,oph,rah,fib,kdj,macd,rsi,ma=",ral,opl,fibl,oph,rah,fib,kdj,macd,rsi,ma
                # ra, fibl,rah,fib,ma,kdj,rsi
                # for x in [boll,kdj,macd,rsi,ma,bollCT,ra,fibl,rah,`]:
                #     print type(x),x
                # print args.dl,ra,fibl,rah,op
                # print ra * fibl + rah*(abs(int(args.dl)-fibl))/fib +ma +kdj+rsi

                diff=eval(ct.powerdiff%(ct.linePowerCountdl))
                print("Diff:%.1f"%(diff))
                cct.sleep(0.1)
                # ts=time.time()
                # time.sleep(5)
                # print "%0.5f"%(time.time()-ts)
            elif code.lower() == 'q' or code.lower() == 'quit' or code.lower() =='exit':
                sys.exit(0)

            elif code == 'h' or code == 'help':
                parser.print_help()

            elif code.startswith('w') or code.startswith('a'):

                if len(dd) > 0:
                    blkname = '077.blk'
                    block_path = tdd.get_tdx_dir_blocknew() + blkname

                    if args.num == 10:
                        args=cct.writeArgmain().parse_args(code.split())
                        writecount = args.dl
                    else:
                        writecount = args.num
                    codew=stf.WriteCountFilter(dd, writecount=writecount)
                    if args.code == 'a':
                        cct.write_to_blocknew(block_path, codew,doubleFile=False,keep_last=0,dfcf=False,reappend=True)
                        # cct.write_to_blocknew(block_path, codew)
                        # cct.write_to_blocknew(all_diffpath,codew)
                        print(("wri append ok:%s" % block_path))
                    else:
                        cct.write_to_blocknew(block_path, codew, append=False,doubleFile=False,keep_last=0,dfcf=False,reappend=True)
                        # cct.write_to_blocknew(all_diffpath,codew,False)
                        print(("wri all ok:%s" % block_path))
                else:
                    print("df is None,not Wri")
            else:
                pass

        except (KeyboardInterrupt) as e:
            # print "key"
            print("KeyboardInterrupt:", e)
        except (IOError, EOFError, Exception) as e:
            # print "Error", e
            import traceback
            traceback.print_exc()
            # sys.exit(0)
    # log.setLevel(LoggerFactory.DEBUG)
    log.setLevel(LoggerFactory.INFO)

    # st=get_linear_model_status('300380',start='2016-01-28',type='h',filter='y')
    st = get_linear_model_status('300380')
    # st=get_linear_model_status('300380',start='2016-01-28',filter='y')
    # maintest('002189',start='2016-01-28',type='h',filter='y')
    print("M:")
    # st=get_linear_model_status('002189',start='2016-01-28',filter='y')
    # maintest('002189',start='2016-01-28',filter='y')
    print("L")
    # st=get_linear_model_status('002189',start='2016-01-28',type='l',filter='y')
    # maintest('002189',start='2016-01-28',type='l',filter='y')
    # cct.set_console(100, 15)











    # elif len(num_input) == 6:
    #                 code = args.code
    #                 # print code, args.ptype, args.dtype, start, end
    #                 lht.get_linear_model_histogramDouble(code, args.ptype, args.dtype, start, end, args.vtype, args.filter)
    #                 # candlestick_powercompute(code,start, end)
    #                 op, ra, st, days = pct.get_linear_model_status(code, start=start, end=end, filter=args.filter)
    #                 print "code:%s op:%s ra:%s  start:%s" % (code, op, ra, st)
    #                 # p=multiprocessing.Process(target=get_linear_model_histogramDouble,args=(code, args.ptype, args.dtype, start, end,args.vtype,args.filter,))
    #                 # p.daemon = True
    #                 # p.start()
    #                 # p.join()
    #                 # time.sleep(6)
    #                 num_input = ''

    #         else:
    #             code = args.code
    #             if len(code) == 6:
    #                 start = cct.day8_to_day10(args.start)
    #                 end = cct.day8_to_day10(args.end)
    #                 get_linear_model_histogramDouble(code, args.ptype, args.dtype, start, end, args.vtype)
    #                 # get_linear_model_histogramDouble(code, args.ptype, args.dtype, start, end, args.vtype)
    #                 # candlestick_powercompute(code,start, end)
    #                 op, ra, st, days = pct.get_linear_model_status(code, start=start, end=end, filter=args.filter)
    #                 print "code:%s op:%s ra:%s  start:%s" % (code, op, ra, st)