# -*- encoding: utf-8 -*-
import json
import os
import re
import sys
import time

sys.path.append("..")
import pandas as pd
import requests

from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct
from JohnsonUtil import LoggerFactory
# import trollius as asyncio
# from trollius.coroutines import From
import asyncio,aiohttp
# log = LoggerFactory.getLogger('Sina_data')
log = LoggerFactory.log
# log.setLevel(LoggerFactory.DEBUG)
from JSONData import tdx_hdf5_api as h5a
from akshare import stock_info_bj_name_code
# pip install --no-deps akshare
# import functools

class StockCode:

    def __init__(self):
        self.start_t = time.time()
        self.STOCK_CODE_PATH = 'stock_codes.conf'
        self.encoding = 'gbk'
        self.stock_code_path = self.stock_code_path()
        self.exceptCount = cct.GlobalValues().getkey('exceptCount')
        # print os.path.getsize(self.stock_code_path)
        if self.exceptCount is None and not os.path.exists(self.stock_code_path) or os.path.getsize(self.stock_code_path) < 500:
            stock_codes = self.get_stock_codes(True)
            print(("create:%s counts:%s" % (self.stock_code_path, len(stock_codes))))
        if self.exceptCount is None and cct.creation_date_duration(self.stock_code_path) > 60:
            stock_codes = self.get_stock_codes(True)
            print(("days:%s %s update stock_codes.conf" % (cct.creation_date_duration(self.stock_code_path), len(stock_codes))))

        

        self.stock_codes = None

    def stock_code_path(self):
        return os.path.join(os.path.dirname(__file__), self.STOCK_CODE_PATH)

    def update_stock_codes(self):
        """获取所有股票 ID 到 all_stock_code 目录下"""
        # 122.10.4.234 www.shdjt.com
        # https://site.ip138.com/www.shdjt.com/
        all_stock_codes_url = 'http://www.shdjt.com/js/lib/astock.js'
        grep_stock_codes = re.compile('~(\d+)`')
        try:
            response = requests.get(all_stock_codes_url)
            response.encoding = self.encoding
        except Exception as e:
            if self.exceptCount is None:
                cct.GlobalValues().setkey('exceptCount',1)
                log.error("Exception:%s"%(e))
            with open(self.stock_code_path) as f:
                self.stock_codes = json.load(f)['stock']
                return self.stock_codes
            # raise e
        
        stock_codes = grep_stock_codes.findall(response.text)
        stock_codes = list(set([elem for elem in stock_codes if elem.startswith(('6', '30', '00','688','43','83','87','92'))]))
        # df=rl.get_sina_Market_json('all')
        # stock_codes = df.index.tolist()
        # '301397'
        stock_info_bj_name_code_df = stock_info_bj_name_code()
        bj_list = stock_info_bj_name_code_df['证券代码'].tolist()
        stock_codes.extend(bj_list)
        with open(self.stock_code_path, 'w') as f:
            f.write(json.dumps(dict(stock=stock_codes)))
        return stock_codes
    # @property

    def get_stock_codes(self, realtime=False):
        """[summary]

        [获取所有股票 ID 到 all_stock_code 目录下]

        Keyword Arguments:
            realtime {bool} -- [description] (default: {False})

        Returns:
            [type] -- [description]
        """
        # print "days:",cct.creation_date_duration(self.stock_code_path)
        if realtime:
            # all_stock_codes_url = 'http://www.shdjt.com/js/lib/astock.js'
            # grep_stock_codes = re.compile('~(\d+)`')
            # response = requests.get(all_stock_codes_url)
            # stock_codes = grep_stock_codes.findall(response.text)
            # stock_codes = [elem for elem in stock_codes if elem.startswith(('6','30','00'))]
            # df=rl.get_sina_Market_json('all')
            # stock_codes = df.index.tolist()
            stock_codes = self.update_stock_codes()
            log.info("readltime codes:%s" % (len(stock_codes)))
            # with open(self.stock_code_path, 'w') as f:
            # f.write(json.dumps(dict(stock=stock_codes)))
            return stock_codes
        else:
            with open(self.stock_code_path) as f:
                self.stock_codes = json.load(f)['stock']
                return self.stock_codes


# -*- encoding: utf-8 -*-
all_func = {'low': 'nlow', 'high': 'nhigh', 'close': 'nclose'}


class Sina:
    """新浪免费行情获取"""

    def __init__(self):
        # self.grep_stock_detail = re.compile(r'(\d+)=([^\S][^,]+?)%s' %
        # (r',([\.\d]+)' * 29,))   #\n特例A (4)
        self.grep_stock_detail = re.compile(
            r'(\d+)=([^\n][^,]+.)%s%s' % (r',([\.\d]+)' * 29, r',(\d{4}-\d{2}-\d{2}),(\d{2}:\d{2}:\d{2})'))
        # r'(\d+)=([^\n][^,]+.)%s' % (r',([\.\d]+)' * 29,))

        # 去除\n特例A(3356)
        # self.grep_stock_detail = re.compile(r'(00\d{4}|30\d{4}|60\d{4})=([^\n][^,]+.)%s' % (r',([\.\d]+)' * 29,))   #去除\n特例A(股票2432)
        # ^(?!64)\d+$
        # self.grep_stock_detail = re.compile(r'([0][^0]\d+.)=([^\n][^,]+.)%s'
        # % (r',([\.\d]+)' * 29,))  # 去除\n特例A(股票2432)
        self.sina_stock_api = 'http://hq.sinajs.cn/?format=text&list='
        self.stock_data = []
        self.stock_codes = []
        self.stock_with_exchange_list = []
        self.max_num = 850
        self.start_t = time.time()
        self.dataframe = pd.DataFrame()
#        self.index_status = False
        self.hdf_name = 'sina_data'
        self.table = 'all'
        self.sina_limit_time = ct.sina_limit_time
        pd.options.mode.chained_assignment = None
        self.cname = False
        self.encoding = 'gbk'
        # cct.get_config_value_ramfile(self.hdf_name,currvalue=time.time(),xtype='time')

        self.sinaheader = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0',
            'referer': 'http://finance.sina.com.cn',
            'Connection': 'keep-alive',
            }
        # # 'Host': 'vip.stock.finance.sina.com.cn',
        # # 'Referer':'http://vip.stock.finance.sina.com.cn',
        # import requests
        # gudaima = "sz300502" #股票代码
        # headers = {'referer': 'http://finance.sina.com.cn'}
        # resp = requests.get('http://hq.sinajs.cn/list=' + gudaima, headers=headers, timeout=6)
        # data = resp.text
        # print(data.split(','))

        # self.lastbuydf = pd.DataFrame()
        # self.all
        # h5 = self.load_hdf_db(table='all', code_l=None, init=True)
        # if h5 is None:
        #     # log.info("hdf5 None")
        #     self.all
        # else:
        #     if not h5.empty and 'time' in h5.columns:
        #         # print  h5[h5.time <> 0].time
        #         if cct.get_work_time() and time.time() - h5[h5.time <> 0].time[0] > ct.h5_limit_time:
        #             self.all

    def get_int_time(self,timet):
        return int(time.strftime("%H:%M:%S",time.localtime(timet))[:6].replace(':',''))

    def load_stock_codes(self):
        with open(self.stock_code_path) as f:
            self.stock_codes = list(set(json.load(f)['stock']))

    # def get_stocks_by_range(self, index):
    #
    #     response = requests.get(self.sina_stock_api + self.stock_list[index])
    #     self.stock_data.append(response.text)

    # def load_hdf_db(self,table='all',code_l=None):
    #     h5=tdd.top_hdf_api(fname=self.hdf_name, table=table, df=None)
    #     if code_l is not None:
    #         if len(code_l) == 0:
    #             return None
    #     if h5 is not None and not h5.empty and 'time' in h5.columns:
    #             o_time = h5[h5.time <> 0].time
    #             if len(o_time) > 0:
    #                 o_time = o_time[0]
    #     #            print time.time() - o_time
    #                 # if cct.get_work_hdf_status() and (not (915 < cct.get_now_time_int() < 930) and time.time() - o_time < ct.h5_limit_time):
    #                 if not cct.get_work_time() or time.time() - o_time < ct.h5_limit_time:
    #                     log.info("time hdf:%s %s"%(self.hdf_name,len(h5))),
    #                     if 'time' in h5.columns:
    #                         # h5=h5.drop(['time'],axis=1)
    #                         if code_l is not None:
    #                             if 'code' in h5.columns:
    #                                 h5 = h5.set_index('code')
    #                             # print [inx for inx in h5.index  if inx not in code_l]
    #                             h5.drop([inx for inx in h5.index  if inx not in code_l], axis=0, inplace=True)
    #                             log.info("time in idx hdf:%s %s"%(self.hdf_name,len(h5))),
    #                     h5=h5.reset_index()
    #                     return h5
    #     else:
    #         if h5 is not None:
    #             return h5
    #     return None

    # def write_hdf_db(self,df,table='all'):
    #     # if 'code' in df.columns:
    #         # df = df.set_index('code')
    #     if df is not None and len(df) > 1000:
    #         dd = df.copy()
    #         if 'code' in dd.columns:
    #             dd = dd.set_index('code')
    #         dd['time'] =  time.time()
    #         h5=tdd.top_hdf_api(fname=self.hdf_name,wr_mode='w', table=table, df=dd)

    @property
    def all(self):

        self.stockcode = StockCode()
        self.stock_code_path = self.stockcode.stock_code_path
        self.stock_codes = self.stockcode.get_stock_codes()
        self.load_stock_codes()
        # print "stocks:",len(self.stock_codes)
        self.stock_codes = [elem for elem in self.stock_codes if elem.startswith(('6', '30', '00','688','43','83','87','92'))]
        time_s = time.time()

        logtime = cct.get_config_value_ramfile(self.hdf_name,xtype='time',readonly=True)

        # otime = int(time.strftime("%H:%M:%S",time.localtime(logtime))[:6].replace(':',''))
        otime = cct.get_config_value_ramfile(self.hdf_name,xtype='time',readonly=True,int_time=True)

        # _sina_data_time = cct.get_config_value_ramfile(self.hdf_name,xtype='time',readonly=True,int_time=True)
        # _sina_logtime =  cct.get_config_value_ramfile('sina_logtime',int_time=True)
        # _now_time = cct.get_now_time_int()

        # if (cct.get_work_time(_sina_data_time) and cct.get_work_time(_sina_logtime)) or ( not cct.get_work_time(_sina_data_time) and not cct.get_work_time(_sina_logtime)):
        #     h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=self.stock_codes, limit_time=self.sina_limit_time)
        # else:
        #     h5 = None

        if (cct.get_work_time(otime) and cct.get_work_time()) or (not cct.get_work_time(otime) and not cct.get_work_time() and ((otime >= 1500) or cct.get_now_time_int() < 1500 ) ):
            h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=self.stock_codes, limit_time=self.sina_limit_time)
        else:
            h5 = None
        log.info("h5a stocksTime:%0.2f" % (time.time() - time_s))
        if h5 is not None and len(h5) > 0:
            o_time = h5[h5.timel != 0].timel
            # o_time = o_time[0] if isinstance(o_time, pd.Series) else o_time
            ticktime = int(h5[h5.ticktime != 0].ticktime[0][-8:-3].replace(":",''))
            if len(o_time) > 0 and ((self.get_int_time(o_time[0]) >= 1500 and ticktime >= 1500) or (self.get_int_time(o_time[0]) < 1500 and ticktime < 1500) ):
                o_time = o_time[0]
                l_time = time.time() - o_time
                sina_limit_time = ct.sina_limit_time
                sina_time_status = (cct.get_work_day_status() and 915 < cct.get_now_time_int() < 926)
#                return_hdf_status = not cct.get_work_day_status() or (cct.get_work_day_status() and (cct.get_work_time() and l_time < sina_limit_time))
                # return_hdf_status = not cct.get_work_time() or (cct.get_work_time() and l_time < sina_limit_time)
                return_hdf_status = (not cct.get_work_time()  and not cct.get_work_time(otime)) or (cct.get_work_time() and l_time < sina_limit_time)
                log.info("915:%s sina_time:%0.2f limit:%s" % (sina_time_status, l_time, sina_limit_time))

                h5 = self.combine_lastbuy(h5)

                if h5 is not None and len(h5) > 0 and  'nclose' in h5.columns and 'nstd' in h5.columns:
                    for co in ['nclose','nstd']:
                        h5[co] = h5[co].apply(lambda x: round(x, 2))
                if 'ticktime' in h5.columns:
                    h5['ticktime'] = pd.to_datetime(h5['ticktime'])
                        
                if sina_time_status and l_time < 6:
                    log.info("open 915 hdf ok:%s" % (len(h5)))
                    return h5
                elif not sina_time_status and return_hdf_status:
                    log.info("return hdf5 data:%s" % (len(h5)))
                    ###update lastbuy data at not worktime
                    return h5
                else:
                    log.info("no return  hdf5:%s" % (len(h5)))
        else:
            log.info("no return  hdf5:%s" % (len(h5) if h5 is not None else 'None'))

        # self.stock_with_exchange_list = list(
            # map(lambda stock_code: ('sh%s' if stock_code.startswith(('5', '6', '9')) else 'sz%s') % stock_code,
            # self.stock_codes))
        # self.stock_with_exchange_list = list(
        #     [('sh%s' if stock_code.startswith(('6')) else 'sz%s') % stock_code for stock_code in self.stock_codes])
        self.stock_with_exchange_list = list(
            [cct.code_to_symbol(stock_code) for stock_code in self.stock_codes])
        self.stock_list = []
        self.request_num = len(self.stock_with_exchange_list) // self.max_num
        for range_start in range(self.request_num):
            num_start = self.max_num * range_start
            num_end = self.max_num * (range_start + 1)
            request_list = ','.join(
                self.stock_with_exchange_list[num_start:num_end])
            self.stock_list.append(request_list)
        # print len(self.stock_with_exchange_list), num_end
        if len(self.stock_with_exchange_list) > num_end:
            request_list = ','.join(
                self.stock_with_exchange_list[num_end:])
            self.stock_list.append(request_list)
            self.request_num += 1
        # a = 0
        # for x in range(self.request_num):
        #     print x
        #     i = len(self.stock_list[x].split(','))
        #     print i
        #     a += i
        #     print a
        log.debug('all:%s' % len(self.stock_list[:5]))
        # log.error('all:%s req:%s' %
        #           (len(self.stock_list), len(self.stock_list)))
        return self.get_stock_data()

    def get_cname_code(self,cname):
        self.cname  = True
        dm = self.all
        df = dm[dm.name == cname]
        if len(df) == 1:
            code = df.index[0]
        else:
            code = 0
        return code

    def get_code_cname(self,code):
        self.cname  = True
        dm = self.all
        df = dm[dm.index == code]
        if len(df) == 1:
            code = df.name[0]
        else:
            code = code
        return code
        
    def market(self, market):
        if market in ['all']:
            return self.all
        else:
            self.stockcode = StockCode()
            self.stock_code_path = self.stockcode.stock_code_path
            self.stock_codes = self.stockcode.get_stock_codes()
            self.load_stock_codes()
            # print type(self.stock_codes)
            # self.stock_with_exchange_list = list(
            # map(lambda stock_code: ('sh%s' if stock_code.startswith(('5', '6', '9')) else 'sz%s') % stock_code,
            # self.stock_codes))        elif market == 'cyb':
            # print len(self.stock_codes)
            # self.stock_codes = [elem for elem in self.stock_codes if elem.startswith(('6','30','00'))]
            # print len(self.stock_codes)
            if market == 'sh':
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('60') or elem.startswith('688')]
                self.stock_with_exchange_list = list(
                    [('sh%s') % stock_code for stock_code in self.stock_codes])
            elif market == 'sz':
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('00')]
                self.stock_with_exchange_list = list(
                    [('sz%s') % stock_code for stock_code in self.stock_codes])
            elif market == 'cyb':
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('30')]
                self.stock_with_exchange_list = list(
                    [('sz%s') % stock_code for stock_code in self.stock_codes])
            elif market == 'kcb':
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('688')]
                self.stock_with_exchange_list = list(
                    [('sz%s') % stock_code for stock_code in self.stock_codes])
            elif market == 'bj':
                # self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('43') or elem.startswith('83') or elem.startswith('87') or elem.startswith('92')]
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith(('43','83','87','92'))]
                self.stock_with_exchange_list = list(
                    [('bj%s') % stock_code for stock_code in self.stock_codes])
            self.stock_codes = list(set(self.stock_codes))

            # _sina_data_time = cct.get_config_value_ramfile(self.hdf_name,xtype='time',readonly=True,int_time=True)
            # _sina_logtime =  cct.get_config_value_ramfile('sina_logtime',int_time=True)
            # _now_time = cct.get_now_time_int()

            # if (cct.get_work_time(_sina_data_time) and cct.get_work_time(_sina_logtime)) or ( not cct.get_work_time(_sina_data_time) and not cct.get_work_time(_sina_logtime)):
            #     h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=self.stock_codes, limit_time=self.sina_limit_time)
            # else:
            #     h5 = None
            time_s= time.time()
            
            h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=self.stock_codes, limit_time=self.sina_limit_time)
            # h5[:1].ticktime.values[0][-8:-3].replace(":",'')
            log.info("h5a market: %s stocksTime:%0.2f" % (market,time.time() - time_s))

            if h5 is not None and len(h5) > 0:
                o_time = h5[h5.timel != 0].timel
                ticktime = int(h5[h5.ticktime != 0].ticktime[0][-8:-3].replace(":",''))
                if len(o_time) > 0 and ((self.get_int_time(o_time[0]) >= 1500 and ticktime >= 1500) or (self.get_int_time(o_time[0]) < 1500 and ticktime < 1500) ):
                    h5 = self.combine_lastbuy(h5)
                    return h5

            self.stock_list = []
            self.request_num = len(self.stock_with_exchange_list) // self.max_num
            for range_start in range(self.request_num):
                num_start = self.max_num * range_start
                num_end = self.max_num * (range_start + 1)
                request_list = ','.join(
                    self.stock_with_exchange_list[num_start:num_end])
                self.stock_list.append(request_list)
            # print len(self.stock_with_exchange_list), num_end
            # if self.request_num == 0:
            #     num_end = self.max_num
            if self.request_num > 0 and len(self.stock_with_exchange_list) > num_end:
                request_list = ','.join(
                    self.stock_with_exchange_list[num_end:])
                self.stock_list.append(request_list)
                self.request_num += 1
            else:
                request_list = ','.join(
                    self.stock_with_exchange_list)
                self.stock_list.append(request_list)
            # a = 0
            # for x in range(self.request_num):
            #     print x
            #     i = len(self.stock_list[x].split(','))
            #     print i
            #     a += i
            #     print a
            # print ('all:%s' % len(self.stock_codes)),
            # log.error('all:%s req:%s' %
            #           (len(self.stock_list), len(self.stock_list)))
            return self.get_stock_data()
    # def get_url_data_R(url):
    #     # headers = {'User-Agent':'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.6) Gecko/20091201 Firefox/3.5.6'}
    #     headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; rv:16.0) Gecko/20100101 Firefox/16.0',
    #                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    #                'Connection': 'keep-alive'}
    #     req = Request(url, headers=headers)
    #     fp = urlopen(req, timeout=5)
    #     data = fp.read()
    #     fp.close()
    #     return data




    # @asyncio.coroutine
    # def get_stocks_by_range_py2(self, index):

    #     # sinaheader = {
    #     #     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0',
    #     #     'Host': 'vip.stock.finance.sina.com.cn',
    #     #     'Referer':'http://vip.stock.finance.sina.com.cn',
    #     #     'Connection': 'keep-alive',
    #     #     }
            
    #     loop = asyncio.get_event_loop()
    #     # response = yield From(loop.run_in_executor(None,self.get_url_data_R,
    #     # (self.sina_stock_api + self.stock_list[index])))

    #     # response = yield From(loop.run_in_executor(None, requests.get, (self.sina_stock_api + self.stock_list[index])))

    #     response = yield From(loop.run_in_executor(None, functools.partial(requests.get, (self.sina_stock_api + self.stock_list[index]) ,headers=self.sinaheader ))  )

    #     response.encoding = self.encoding
    #     # response = yield (requests.get(self.sina_stock_api + self.stock_list[index]))
    #     # log.debug("url:%s"%(self.sina_stock_api + self.stock_list[index]))
    #     # log.debug("res_encoding:%s" % response.encoding[:10])
    #     if len(response.text) < 10:
    #         log.error("response.text is None:%s"%(response.text))
    #     self.stock_data.append(response.text)
    #     # Return(self.stock_data.append(response.text))


    # https://github.com/jinrongxiaoe/easyquotation
    async def get_stocks_by_range(self, index):

        # loop = asyncio.get_event_loop()
        # response = yield From(loop.run_in_executor(None,self.get_url_data_R,
        # (self.sina_stock_api + self.stock_list[index])))
        # response = yield From(loop.run_in_executor(None, requests.get, (self.sina_stock_api + self.stock_list[index])))
        # session = aiohttp.ClientSession(timeout=30)


        # session = aiohttp.ClientSession()
        # response = await session.get(self.sina_stock_api + self.stock_list[index])
        # response.encoding = self.encoding
        # result = await response.text()
        # await session.close()

        url = self.sina_stock_api + self.stock_list[index]
        async with aiohttp.ClientSession() as session:
                response = await session.get(url=url,headers=self.sinaheader)
                headers = response.headers
                response.encoding = self.encoding
                result = await response.text()
                await session.close()
                # print(u, headers)
                # return headers


        # response = await aiohttp.get(self.sina_stock_api + self.stock_list[index])
        # response = yield (requests.get(self.sina_stock_api + self.stock_list[index]))
        # log.debug("url:%s"%(self.sina_stock_api + self.stock_list[index]))
        # log.debug("res_encoding:%s" % response.encoding[:10])
        # await asyncio.as_completed(response)
        self.stock_data.append(result)
        # Return(self.stock_data.append(response.text))

    def get_stock_data(self, retry_count=3, pause=0.01):
        threads = []
        for index in range(self.request_num):
            threads.append(self.get_stocks_by_range(index))
            log.debug("url len:%s" %
                      (len(self.stock_list[index])))
        if self.request_num == 0:
            threads.append(self.get_stocks_by_range(0))

        for _ in range(retry_count):
            time.sleep(pause)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(asyncio.wait(threads))
            # asyncio.run(asyncio.wait(threads))
            # loop.close()
            log.debug('get_stock_data_loop')
            return self.format_response_data()

        raise IOError(ct.NETWORK_URL_ERROR_MSG)


    # def get_stock_data_py2(self, retry_count=3, pause=0.01):
    #     threads = []
    #     for index in range(self.request_num):
    #         threads.append(self.get_stocks_by_range(index))
    #     if self.request_num == 0:
    #         threads.append(self.get_stocks_by_range(0))
    #     for _ in range(retry_count):
    #         time.sleep(pause)
    #         try:
    #             loop = asyncio.get_event_loop()
    #         except RuntimeError:
    #             loop = asyncio.new_event_loop()
    #             asyncio.set_event_loop(loop)
    #         loop.run_until_complete(asyncio.wait(threads))
    #         log.debug('get_stock_data_loop')
    #         return self.format_response_data()
    #     raise IOError(ct.NETWORK_URL_ERROR_MSG)


    # def get_stock_data(self):
    #     threads = []
    #     for index in range(self.request_num):
    #         threads.append(index)
    #
    #     # cct.to_mp_run(self.get_stocks_by_range, threads)
    #
    #     return self.format_response_data()
    def lastbuy_timeout_status(self,logtime):

        return (time.time() - float(logtime) > float(ct.sina_lastbuy_logtime))

    def combine_lastbuy(self,h5):
        # if not self.cname and cct.get_now_time_int() > 925:
        time_s= time.time()
        # if cct.get_now_time_int() > 925:
        if not self.cname and cct.get_work_time() and cct.get_now_time_int() > 925:
            h5_fname = 'sina_MultiIndex_data'
            h5_table = 'all' + '_' + str(ct.sina_limit_time)
            fname = 'sina_logtime'
            logtime = cct.get_config_value_ramfile(fname)
            # if logtime <> 0 and not cct.get_work_time():
            h5 = h5.fillna(0)
            if logtime != 0:

                if 'lastbuy' not in h5.columns or len(h5[h5.lastbuy < 0]) > 0:
                    if  cct.GlobalValues().getkey('lastbuydf')  is None:
                        h5_a = h5a.load_hdf_db(h5_fname, h5_table, timelimit=False)
                        if h5_a is not None and 'lastbuy' in h5_a.columns:
                            lastbuycol = h5_a.lastbuy.groupby(level=[0]).tail(1).reset_index().set_index('code').lastbuy
                            h5 = cct.combine_dataFrame(h5,lastbuycol)
                            cct.GlobalValues().setkey('lastbuydf', lastbuycol)
                            # h5['lastbuy'] = (map(lambda x, y: y if int(x) == 0 else x,h5['lastbuy'].values, h5['llastp'].values))
                    else:
                        h5 = cct.combine_dataFrame(h5,cct.GlobalValues().getkey('lastbuydf'))
                # else:
                #     h5['lastbuy'] = (list(map(lambda x, y: y if int(x) == 0 else x,
                #                              h5['lastbuy'].values, h5['close'].values)))
        time_use=round((time.time()-time_s),1)
        if time_use > 2:
            print("lastb:%s"%(time_use), end=' ')

        if 'lastbuy' in h5:
            if h5.lastbuy[-1] < 0:
                if 'nclose' in h5.columns and h5.nclose[-1] > 0:
                    h5.lastbuy = h5.nclose
                else:
                    h5.lastbuy = h5.close
        return h5

    def set_stock_codes_index_init(self, code, index=False):
        if not isinstance(code, list):
            code = code.split(',')
        code_l = []
        if index:
            if isinstance(code, list):
                for x in code:
                    if x.startswith('999'):
                        code_l.append(str(1000000 - int(x)).zfill(6))
                    else:
                        code_l.append(x)
                # self.stock_codes = map(lambda stock_code: (
                # 'sh%s' if stock_code.startswith(('0')) else 'sz%s') % stock_code, code_l)

#            else:
#                if isinstance(code,str) and code.startswith('999'):
#                    code = '000001'
#                    code_l = code.split()
            self.stock_codes = [(
                'sh%s' if stock_code.startswith(('0')) else 'sz%s') % stock_code for stock_code in code_l]

        else:
            code_l = code
            # self.stock_codes = [('sh%s' if stock_code.startswith(
            #     ('5', '6', '9')) else 'sz%s') % stock_code for stock_code in code_l]
            self.stock_codes = [cct.code_to_symbol(stock_code) for stock_code in code_l]
        return code_l

    def get_stock_code_data(self, code, index=False):

        #        self.stock_codes = code
        # self.stock_with_exchange_list = list(
        #     map(lambda stock_code: ('sh%s' if stock_code.startswith(('5', '6', '9')) else 'sz%s') % stock_code,
        #         ulist))
        #        self.index_status = index
        code_l = self.set_stock_codes_index_init(code, index)
        h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=code_l, index=index, limit_time=self.sina_limit_time)
        if h5 is not None:
            log.info("find index hdf5 data:%s" % (len(h5)))
            h5 = self.combine_lastbuy(h5)
            return h5
#        else:
#            h5 = h5a.load_hdf_db(self.hdf_name,self.table, code_l=code_l,index=index)
#            if h5 is not None:
#                log.info("not index hdf5 data:%s"%(len(h5)))
#                return h5
        self.stock_data = []
        self.url = self.sina_stock_api + ','.join(self.stock_codes)
        log.info("stock_list:%s" % self.url[:30])
        response = requests.get(self.url,headers=self.sinaheader)
        response.encoding = self.encoding
        self.stock_data.append(response.text)
        self.dataframe = self.format_response_data(index)
        # self.get_tdx_dd()
        return self.dataframe


    def get_stock_list_data(self, ulist, index=False):

        #        self.index_status = index
        # ulist1 = [stock_code if stock_code.startswith(('0','3','5', '6', '9')) for stock_code in ulist]  # SyntaxError: invalid syntax
        ulist = [stock_code  for stock_code in ulist if stock_code.startswith(('0','3','4','5', '6','8', '9'))]
        if index:
            ulist = self.set_stock_codes_index_init(ulist, index)
            h5 = None
        else:
            h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=ulist, index=index)
        if h5 is not None and len(h5) >= len(ulist):
            log.info("hdf5 data:%s" % (len(h5)))
            h5 = self.combine_lastbuy(h5)
            return h5

        self.stock_data = []
        if len(ulist) > self.max_num:
            # print "a"
            self.stock_list = []
            # self.stock_with_exchange_list = list(
            #     [('sh%s' if stock_code.startswith(('5', '6', '9')) else 'sz%s') % stock_code for stock_code in ulist])
            self.stock_with_exchange_list = list(
                [ cct.code_to_symbol(stock_code)  for stock_code in ulist])
            self.request_num = len(
                self.stock_with_exchange_list) // self.max_num
            for range_start in range(self.request_num):
                num_start = self.max_num * range_start
                num_end = self.max_num * (range_start + 1)
                request_list = ','.join(
                    self.stock_with_exchange_list[num_start:num_end])
                self.stock_list.append(request_list)
            if len(self.stock_with_exchange_list) > num_end:
                request_list = ','.join(
                    self.stock_with_exchange_list[num_end:])
                self.stock_list.append(request_list)
                self.request_num += 1

            log.debug('all:%s' % len(self.stock_list))
            return self.get_stock_data()
        else:
            if not index:
                self.stock_codes = ulist
                # self.stock_with_exchange_list = list(
                #     map(lambda stock_code: ('sh%s' if stock_code.startswith(('5', '6', '9')) else 'sz%s') % stock_code,
                #         ulist))
                # print self.stock_codes
                self.stock_codes = [ cct.code_to_symbol(stock_code)  for stock_code in ulist]

            if len(self.stock_codes) == 0:
                log.error("self.stock_codes is None:%s"%(self.stock_codes))
            self.url = self.sina_stock_api + ','.join(self.stock_codes)
            log.info("stock_list:%s" % self.url[:30])
            response = requests.get(self.url,headers=self.sinaheader)
            response.encoding = self.encoding
            self.stock_data.append(response.text)
            self.dataframe = self.format_response_data(index)
        # self.get_tdx_dd()
        return self.dataframe

    # def get_tdx_dd(self):
    #     df = tdd.get_tdx_all_day_LastDF(self.stock_codes)
        # print df

    def get_col_agg_df(self, h5, dd, run_col, all_func, startime, endtime, freq=None):
        if isinstance(run_col, list):
            now_col = [all_func[co] for co in run_col if co in list(all_func.keys())]
        else:
            now_col = [all_func[co] for co in list(run_col.keys()) if co in list(all_func.keys())]
        now_func = cct.from_list_to_dict(run_col, all_func)
        if h5 is not None and len(h5) > len(dd):
            time_n = time.time()
            # h5 = cct.get_limit_multiIndex_Group(h5, freq=freq,end=endtime)
            # import pdb;pdb.set_trace()
            if freq is None:
                h5 = cct.get_limit_multiIndex_Row(h5, col=run_col, start=startime, end=endtime)
            else:
                h5 = cct.get_limit_multiIndex_freq(h5, freq=freq, col=run_col, start=startime, end=endtime)
                h5 = h5.groupby(level=[0]).tail(1)
            # h5 = cct.get_limit_multiIndex_Row(h5,col=run_col,start=startime, end=endtime)
            if h5 is not None and len(h5) > 0:
                h5 = h5.reset_index().set_index('code')
                h5.rename(columns=now_func, inplace=True)
                # log.info("get_limit_multiIndex_Row:%s  endtime:%s" % (len(h5), endtime))
                #h5 = h5.drop(['ticktime'], axis=1)
                h5 = h5.loc[:, now_col]
                dd = cct.combine_dataFrame(dd, h5, col=None, compare=None, append=False, clean=True)
                log.info('agg_df_Row:%.2f h5:%s endtime:%s' % ((time.time() - time_n), len(h5), endtime))
        return dd

    def format_response_data(self, index=False):
        stocks_detail = ''.join(self.stock_data)
        # print stocks_detail
        result = self.grep_stock_detail.finditer(stocks_detail)
        # stock_dict = dict()
        list_s = []
        for stock_match_object in result:
            stock = stock_match_object.groups()
            # print stock
            # print stock
            # fn=(lambda x:x)
            # list.append(map(fn,stock))
            # df = pd.DataFrame(list,columns=ct.SINA_Total_Columns)
            #     list_s.append({'code'})
            list_s.append(
                {'code': stock[0],
                 'name': stock[1],
                 'open': float(stock[2]),
                 'close': float(stock[3]),
                 'now': float(stock[4]),
                 'high': float(stock[5]),
                 'low': float(stock[6]),
                 'buy': float(stock[7]),
                 'sell': float(stock[8]),
                 'volume': int(stock[9]),
                 'turnover': float(stock[10]),  #交易额/亿
                 # 'turnover': round(float(stock[10])/1000/1000/100,1),  #交易额/亿
                 # 'amount': float(stock[10]),
                 'b1_v': int(stock[11]),
                 'b1': float(stock[12]),
                 'b2_v': int(stock[13]),
                 'b2': float(stock[14]),
                 'b3_v': int(stock[15]),
                 'b3': float(stock[16]),
                 'b4_v': int(stock[17]),
                 'b4': float(stock[18]),
                 'b5_v': int(stock[19]),
                 'b5': float(stock[20]),
                 'a1_v': int(stock[21]),
                 'a1': float(stock[22]),
                 'a2_v': int(stock[23]),
                 'a2': float(stock[24]),
                 'a3_v': int(stock[25]),
                 'a3': float(stock[26]),
                 'a4_v': int(stock[27]),
                 'a4': float(stock[28]),
                 'a5_v': int(stock[29]),
                 'a5': float(stock[30]),
                 'dt': (stock[31]),
                 'ticktime': (stock[32])})
#        print list_s
        # df = pd.DataFrame.from_dict(stock_dict,columns=ct.SINA_Total_Columns)
        if len(list_s) == 0:
            log.error("Sina Url error:%s"%(self.sina_stock_api + ','.join(self.stock_codes[:2])))

        df = pd.DataFrame(list_s, columns=ct.SINA_Total_Columns)
        # if self.index_status and cct.get_work_time():
        # if self.index_status:
        # if cct.get_work_time() or (cct.get_now_time_int() > 915) :
        # df = df.drop('close', axis=1)
        dt = df.dt.value_counts().index[0]
        df = df[(df.dt >= dt)]

        df.rename(columns={'close': 'llastp'}, inplace=True)
        df['b1_vv'] = df['b1_v'].map(lambda x: int(x/100/10000))
        if (cct.get_now_time_int() > 915 and cct.get_now_time_int() < 926):
            #            df.rename(columns={'buy': 'close'}, inplace=True)
            df['close'] = df['buy']
            df['low'] = df['buy']
            df['volume'] = ((df['b1_v'] + df['b2_v'])).map(lambda x: x)
            # df['b1_v'] = ((df['b1_v'] + df['b2_v']) / 100 / 10000).map(lambda x: round(x, 1) + 0.01)
            # df['b1_v'] = ((df['b1_v']) / 100 / 10000).map(lambda x: round(x, 1) + 0.01)
            # df['b1_vv'] = map(lambda x: round(x / 100 / 10000, 1) + 0.01, df['b1_v'])

        elif (cct.get_now_time_int() > 0 and cct.get_now_time_int() <= 915):
            #            df.rename(columns={'buy': 'close'}, inplace=True)
            df['buy'] = df['now']
            df['close'] = df['buy']
            df['low'] = df['buy']
            # df['b1_v'] = ((df['b1_v']) / df['volume'] * 100).map(lambda x: round(x, 1))

        else:
            # df['b1_v'] = ((df['b1_v']) / df['volume'] * 100).map(lambda x: round(x, 1))
            # df.rename(columns={'now': 'close'}, inplace=True)
            df['close'] = df['now']

        df['nvol'] = df['volume']
        df = df.drop_duplicates('code')
        # df = df.loc[:, ct.SINA_Total_Columns_Clean]
        # df = df.loc[:, ct.SINA_Total_Columns]
        # df.rename(columns={'turnover': 'amount'}, inplace=True)
        df = df.fillna(0)
#        df = df.sort_values(by='code', ascending=0)
        df = df.set_index('code')
        if index:
            df.index = list(map((lambda x: str(1000000 - int(x))
                            if x.startswith('0') else x), df.index))
        # print ("Market-df:%s %s time: %s" % (
        # cct.get_now_time()))
        log.info("hdf:all%s %s" % (len(df), len(self.stock_codes)))
        dd = df.copy()
        h5_fname = 'sina_MultiIndex_data'
        h5_table = 'all' + '_' + str(ct.sina_limit_time)
        fname = 'sina_logtime'
        logtime = cct.get_config_value_ramfile('sina_logtime')
        # otime = int(time.strftime("%H:%M:%S",time.localtime(logtime))[:6].replace(':',''))
        otime =  cct.get_config_value_ramfile('sina_logtime',int_time=True)

        # if cct.get_now_time_int() > 925 and not index and len(df) > 3000 and ( 924 < otime < 1500 or cct.get_work_time()):

        # if cct.is_trade_date() and cct.get_now_time_int() > 925 and (not index and len(df) > 3000 and ( cct.get_work_time(otime) or cct.get_work_time())):
        if cct.get_now_time_int() > 925 and (not index and len(df) > 3000 and ( cct.get_work_time(otime) or cct.get_work_time())):
            time_s = time.time()
            df.index = df.index.astype(str)
            df.ticktime = df.ticktime.astype(str)
            # df.ticktime = map(lambda x: int(x.replace(':', '')), df.ticktime)
            df.ticktime = list(map(lambda x, y: str(x) + ' ' + str(y), df.dt, df.ticktime))
            df.ticktime = pd.to_datetime(df.ticktime, format='%Y-%m-%d %H:%M:%S')

            # df = df.loc[:, ['open', 'high', 'low', 'close', 'llastp', 'volume', 'ticktime']]
            # config_ini = cct.get_ramdisk_dir() + os.path.sep+ 'h5config.txt'

            if logtime == 0:
                duratime = cct.get_config_value_ramfile(fname,currvalue=time.time(),xtype='time',update=True)
                df['lastbuy'] = (list(map(lambda x, y: y if int(x) == 0 else x,
                                          df['close'].values, df['llastp'].values)))
                cct.GlobalValues().setkey('lastbuydf', df['lastbuy']) 

            else:
                
                if (cct.GlobalValues().getkey('lastbuylogtime') is not None ) or self.lastbuy_timeout_status(logtime):
                # if cct.get_now_time_int() - cct.GlobalValues().getkey('logtime') > ct.sina_lastbuy_logtime:
                    duratime = cct.get_config_value_ramfile(fname,currvalue=time.time(),xtype='time',update=True)
                    # df[['llastp','close','lastbuy']][:10]
                    df['lastbuy'] = (list(map(lambda x, y: y if int(x) == 0 else x,
                                              df['close'].values, df['llastp'].values)))
                    cct.GlobalValues().setkey('lastbuylogtime', None) 
                    cct.GlobalValues().setkey('lastbuydf', df['lastbuy']) 
                else:
                    df = self.combine_lastbuy(df)
            #top_temp.loc['600903'][['lastbuy','now']]
            #spp.all_10.loc['600074'].lastbuy
            #spp.all_10.lastbuy.groupby(level=[0]).tail(1).reset_index().set_index('code')[-50:]
            dd = df.copy()

            if 'lastbuy' in df.columns:
                df = df.loc[:, ['close', 'high', 'low', 'llastp', 'volume', 'ticktime','lastbuy']]
            else:
                df = df.loc[:, ['close', 'high', 'low', 'llastp', 'volume', 'ticktime']]
                df['lastbuy'] = df['close']
            # df['muclose'] = df['close']

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


        if ('nlow' not in df.columns or 'nhigh' not in df.columns) and  (cct.get_work_time() and 924 < cct.get_now_time_int() <= 1501):
            # if 'nlow' not in df.columns or 'nhigh' not in df.columns or cct.get_work_time():
            h5 = h5a.load_hdf_db(h5_fname, h5_table, timelimit=False)

            time_s = time.time()
            if cct.get_work_time() and cct.get_now_time_int() <= 945:
                run_col = ['low', 'high', 'close']
                startime = '09:24:00'
                # endtime = '10:00:00'
                endtime = '09:45:00'
                dd = self.get_col_agg_df(h5, dd, run_col, all_func, startime, endtime)
                startime = '09:24:00'
                # endtime = '10:00:00'
                endtime = '09:45:00'
                run_col = {'close': 'std'}
                dd = self.get_col_agg_df(h5, dd, run_col, run_col, startime, endtime)
                dd.rename(columns={'std': 'nstd'}, inplace=True)
                if dd is not None and len(dd) > 0 and  'nclose' in dd.columns and 'nstd' in dd.columns:
                    for co in ['nclose','nstd']:
                        dd[co] = dd[co].apply(lambda x: round(x, 2))

            else:
                run_col = ['low','high']
                startime = '09:24:00'
                # endtime = '10:00:00'
                endtime = '09:45:00'
                dd = self.get_col_agg_df(h5, dd, run_col, all_func, startime, endtime)

                # run_col = ['high']
                # startime = '09:24:00'
                # endtime = '10:30:00'
                # dd = self.get_col_agg_df(h5, dd, run_col, all_func, startime, endtime)

                startime = '09:24:00'
                endtime = '15:01:00'
                run_col = ['close']
                # h5 = cct.get_limit_multiIndex_Group(h5, freq='15T', col=run_col,start=startime, end=endtime)
                # time_s=time.time()
                dd = self.get_col_agg_df(h5, dd, run_col, all_func, startime, endtime)
                # run_col = {'close': 'std'}
                # dd = self.get_col_agg_df(h5, dd, run_col, run_col, startime, endtime)
                # dd.rename(columns={'std': 'nstd'}, inplace=True)
                # if dd is not None and len(dd) > 0 and  'nclose' in dd.columns and 'nstd' in dd.columns:
                #     for co in ['nclose','nstd']:
                #         dd[co] = dd[co].apply(lambda x: round(x, 2))
            # if 'nstd' in dd.columns:
            #     dd['stdv'] = map(lambda x, y: round(x / y * 100, 1), dd.nstd, dd.open)

            # if h5 is not None and 'lastbuy' in h5.columns:
            #     lastbuycol = h5.lastbuy.groupby(level=[0]).tail(1).reset_index().set_index('code').lastbuy
            #     dd = cct.combine_dataFrame(dd,lastbuycol)

            log.info("agg_df_all_time:%0.2f" % (time.time() - time_s))
            # top_temp[:1][['high','nhigh','low','nlow','close','nclose','llastp']]



        h5a.write_hdf_db(self.hdf_name, dd, self.table, index=index)
        # if cct.get_config_value_ramfile('sina_logtime',int_time=True) 
        logtime = cct.get_config_value_ramfile(self.hdf_name,currvalue=time.time(),xtype='time',update=True)
        log.info("wr end:%0.2f" % (time.time() - self.start_t))
        # print df['lastbuy','close'][-5:].to_frame().T
        # print "logtime:",time.strftime("%H:%M:%S",time.localtime(logtime)),"time:",time.time() - float(logtime)
        # if 'lastbuy' in df.columns:
        #     print df[-5:][['lastbuy','close']].T
        dd = self.combine_lastbuy(dd)

        if dd is not None and len(dd) > 0 and  'nclose' in dd.columns and 'nstd' in dd.columns:
            for co in ['nclose','nstd']:
                dd[co] = dd[co].apply(lambda x: round(x, 2))
        if 'ticktime' in dd.columns:
            dd['ticktime'] = pd.to_datetime(dd['ticktime'])
            
        return dd
        # df = pd.DataFrame.from_dict(stock_dict, orient='columns',
        #                             columns=['name', 'open', 'close', 'now', 'high', 'low', 'buy', 'sell', 'turnover',
        #                                      'volume', 'bid1_volume', 'bid1', 'bid2_volume', 'bid2', 'bid3_volume',
        #                                      'bid3', 'bid4_volume', 'bid4', 'bid5_volume', 'bid5', 'ask1_volume',
        #                                      'ask1', 'ask2_volume', 'ask2', 'ask3_volume', 'ask3', 'ask4_volume',
        #                                      'ask4', 'ask5_volume', 'ask5'])
        # return stock_dict


def nanrankdata_len(x):
    time_s = time.time()
    df = get_tdx_stock_period_to_type(x, period_day='5T')
    print(('t:%0.2f' % (time.time() - time_s)))
    return df

if __name__ == "__main__":
    times = time.time()
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

    # log.setLevel(LoggerFactory.DEBUG)
    sina = Sina()
    # print len(df)
    # code='300107'
    # print sina.get_cname_code('陕西黑猫')
    # print((sina.get_stock_code_data('300502').turnover))
    # print((sina.get_stock_code_data('002190').T))

    # print(sina.get_code_cname('301397'))

    # print(sina.get_code_cname('300107'))
    # print((sina.get_stock_code_data('000017').T))

    # print((sina.get_stock_code_data('300107').T))

    df =sina.all
    print(len(df))
    print(f"df.loc['002786']: {df.loc['002786']}")
    import ipdb;ipdb.set_trace()

    for ma in ['bj','sh', 'sz', 'cyb', 'kcb','all']:
        # for ma in ['sh']:
        df = Sina().market(ma)
        # print df.loc['600581']
        # print len(sina.all)
        print(("market:%s %s" % (ma, len(df))))

        
    # print df.lastbuy[-5:].to_frame().T
    print((sina.get_stock_list_data(['999999','399001','399006'],index=True).name))
    # df = sina.get_stock_code_data('999999',index=True)
    print((df.name))

    df = Sina().market('cyb')
    print((df.shape))

    # print((sina.get_stock_code_data('000017').T))
    # import ipdb;ipdb.set_trace()
    print((sina.get_stock_code_data('430017').T))
    print((df[-5:][['open','close']].T))
    print((df.columns))
    # print df[-5:][['lastbuy','close']].T


    # df = sina.get_stock_code_data('000001',index=True).set_index('code')
    # df= sina.get_stock_code_data('999999,399001',index=True)
    sys.exit(0)
    code_agg = '601939'
    dd = sina.get_stock_code_data([code_agg,'600050','002350', '601899',\
      '603363','000868','603917','600392','300713','000933','002505','603676'])
    print((dd.T))

    print((dd.loc[:, ['name','open','low','high','close', 'nclose', 'nlow', 'nhigh', 'nstd', 'ticktime']], dd.shape))
    # print dd.loc[code_agg].T

    # print df.columns
    # df = sina.all
    # print df.nlow[:5]
    # print sina.get_stock_code_data('600199,300334',index=False)
    # print len(sina.market('sh'))

    # def compute_lastdays_percent(df=None, step=3):
    #     if df is not None and len(df) > step:
    #         df = df.sort_index(ascending=True)
    #         # if cct.get_work_day_status() and 915 < cct.get_now_time_int() < 1500:
    #         # df = df[df.index < cct.get_today()]
    #         df = df.fillna(0)
    #         da = step
    #         if 'close' in df.columns:
    #             df['lastp%sd' % da] = df['close'].shift(da)
    #         if 'volume' in df.columns:
    #             df['lastv%sd' % da] = df['volume'].shift(da)
    #         if 'close' in df.columns and 'lastp%sd' % da in df.columns:
    #             df['per%sd' % da] = ((df['close'] - df['lastp%sd' % da]) / df['lastp%sd' % da]).map(lambda x: round(x * 100, 2))
    #         if 'volume' in df.columns and 'lastv%sd' % da in df.columns:
    #             df['vol%sd' % da] = ((df['volume'] - df['lastv%sd' % da])).map(lambda x: round(x / 100, 1))
    #     else:
    #         log.info("compute df is none")
    #     return df

    def get_col_agg_df_Test(h5, dd, run_col, all_func, startime, endtime, freq=None):
        if isinstance(run_col, list):
            now_col = [all_func[co] for co in run_col if co in list(all_func.keys())]
        else:
            now_col = [all_func[co] for co in list(run_col.keys()) if co in list(all_func.keys())]
        now_func = cct.from_list_to_dict(run_col, all_func)
        if h5 is not None and len(h5) > len(dd):
            time_n = time.time()
            # h5 = cct.get_limit_multiIndex_Group(h5, freq=freq,end=endtime)
            ts = time.time()
            if freq is None:
                h5 = cct.get_limit_multiIndex_Row(h5, col=run_col, start=startime, end=endtime)
            else:
                h5 = cct.get_limit_multiIndex_freq(h5, freq=freq, col=run_col, start=startime, end=endtime)
                h5 = h5.groupby(level=[0]).tail(1)
            # h5 = h5.groupby(level=[0]).tail(1)
            print(("s:", round(time.time() - ts, 2), len(h5)))
            if h5 is not None and len(h5) > 0:
                h5 = h5.reset_index().set_index('code')
                h5.rename(columns=now_func, inplace=True)
                # log.info("get_limit_multiIndex_Row:%s  endtime:%s" % (len(h5), endtime))
                #h5 = h5.drop(['ticktime'], axis=1)
                h5 = h5.loc[:, now_col]
                dd = cct.combine_dataFrame(dd, h5, col=None, compare=None, append=False, clean=True)
                log.info('agg_df_Row:%.2f h5:%s endtime:%s' % ((time.time() - time_n), len(h5), endtime))
        return dd
    h5_fname = 'sina_MultiIndex_data'
    # h5_fname = 'sina_multi_index'
    h5_table = 'all_10'
    time_s = time.time()
    h5 = h5a.load_hdf_db(h5_fname, table=h5_table, code_l=None, timelimit=False, dratio_limit=0.12)
    print(('h5:', len(h5)))
    if cct.get_work_time() and cct.get_now_time_int() <= 1000:
        run_col = ['low', 'high', 'close']
        startime = None
        # endtime = '10:00:00'
        endtime = '09:45:00'
        dd = get_col_agg_df_Test(h5, dd, run_col, all_func, startime, endtime)
    else:
        run_col = ['low', 'high']
        startime = None
        # endtime = '10:00:00'
        endtime = '09:45:00'
        dd = get_col_agg_df_Test(h5, dd, run_col, all_func, startime, endtime)

        startime = '09:30:00'
        endtime = '15:01:00'
        # run_col = ['close']
        # all_func = {'low': 'nlow', 'high': 'nhigh', 'close': 'nclose'}

        # run_col = ['low']
        # all_func = {'low': 'nlow', 'high': 'nhigh', 'close': 'nclose'}

        # all_func = {'low': 'mean'}
        # h5 = cct.get_limit_multiIndex_Group(h5, freq='15T', col=run_col,start=startime, end=endtime)
        run_col = {'close': 'std'}
        dd = get_col_agg_df_Test(h5, dd, run_col, run_col, startime, endtime)
        dd.rename(columns={'std': 'nstd'}, inplace=True)

        # dd = get_col_agg_df_Test(h5, df, run_col, all_func, startime, endtime,'15T')
        # ts =  time.time()
        # tt = h5.groupby([h5.index.get_level_values(i) for i in [0]] + [pd.Grouper(freq='15T', level=-1, closed='right', label='right')]).mean()
        # print "tts:",round(time.time()-ts,2),len(tt)

    print((dd.loc['600007', ['close', 'nclose', 'nlow', 'nhigh', 'nstd', 'ticktime']], dd.shape))
    print((dd.loc[:, ['close', 'nclose', 'nlow', 'nhigh', 'nstd', 'ticktime']], dd.shape))
    '''
    if df is not None and len(df) > 0:
        print df[:1]
        stock_data = df
        print "t1:%0.3f df:%s" % (time.time() - time_s, df.shape)
        # df = cct.using_Grouper_eval(df, freq='5T', col=['low','close'], closed='right', label='right')
        # dd = cct.get_limit_multiIndex_Group(df, freq='15T', col=['low', 'close'], index='ticktime', end='09:45:00')
        dd = cct.get_limit_multiIndex_Row(df, freq='15T', col=['low', 'high'], index='ticktime', end='09:45:00')
        # df = using_Grouper(df, freq='5T')
        # stock_data = stock_data.reset_index().set_index('ticktime')
        # df = stock_data.groupby('code').resample('5T', how={'low': 'min', 'close':'min', 'volume': 'sum'})
        print "t2:%0.3f df:%s" % (time.time() - time_s, dd.shape)
        print dd.loc['600191'][-2:]
        df = cct.using_Grouper(df, freq='15T', col=['low', 'high'], closed='right', label='right')
        # df = using_Grouper(df, freq='30T')

        # df = stock_data.groupby('code').resample('30T', how={'low': 'min', 'close':'min', 'volume': 'sum'})
        # df = df.groupby(level=0).transform(get_tdx_stock_period_to_type)
        # df = df.groupby([df.index.get_level_values(i) for i in [0]]+[pd.Grouper(freq='30T', level=-1)]).transform(get_tdx_stock_period_to_type)
        print "t3:%0.3f df:%s" % (time.time() - time_s, df.shape)
        print df.loc['300081'][-2:]
    '''
    # print df.groupby(pd.Grouper(freq='30T', level='ticktime'))
    # df.groupby(level=0)['low'].transform('min').loc['600805'][:5]
    # print df.groupby(level=0).transform(nanrankdata_len)[:10]
    # import pandas as pd
    # df = pd.HDFStore(cct.get_ramdisk_path(h5_fname))[h5_table]
    sys.exit(0)
    code = '300248'
    # code = '000099'
    # print "t:", round(time.time() - time_s, 1),
    if df is not None and len(df) > 0 and code in df.index:
        df = compute_lastdays_percent(df=df.loc[code], step=1)
        # print df[df.index < '09:32:00']
        print((df[-1:], round(time.time() - time_s, 1)))
    # sys.exit(0)
    time_s = time.time()
    dd = pd.DataFrame()
    # st=h5a.get_hdf5_file(f_name, wr_mode='w', complevel=9, complib='zlib',mutiindx=True)
    for ma in ['sh', 'sz', 'cyb', 'all']:
        # for ma in ['sh']:
        df = Sina().market(ma)
        # print df.loc['600581']
        # print len(sina.all)
        print(("market:%s %s" % (ma, len(df))))

    h5_fname = 'sina_multi_index'
    dl = 30
    h5_table = 'all' + '_' + str(10)
    # df = Sina().market('all')
    df = ''
    if 1 and len(df) > 0:
        # stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
        # period_stock_data.index = map(lambda x: str(x)[:10], period_stock_data.index)
        # df.index = map(lambda x: x.replace('-', '').replace('\n', ''), df.index)
        # df.index = pd.to_datetime(df.index, format='%Y-%m-%d')
        df.index = df.index.astype(str)
        # df.index.name = 'date'
        # df.index = df.index.astype(int)
        # df.ticktime = df.ticktime.astype(str)
        # df.ticktime = pd.to_datetime(df.ticktime, format='%H:%M:%S').dt.time()
        # price change  volume   amount type

        # df.ticktime = map(lambda x: int(x.replace(':', '')), df.ticktime)
        df.ticktime = list(map(lambda x, y: str(x) + ' ' + str(y), df.dt, df.ticktime))
        print((df.ticktime[:3]))
        df.ticktime = pd.to_datetime(df.ticktime, format='%Y-%m-%d %H:%M:%S')
        print((df.ticktime[:2]))
        # sys.exit(0)
        # df = df.loc[:, ['open', 'high', 'low', 'close', 'llastp', 'volume', 'ticktime']]
        # df = df.loc[:, ['open', 'high', 'low', 'close', 'llastp', 'volume', 'ticktime']]
        df = df.loc[:, ['close', 'high', 'low', 'llastp', 'volume', 'ticktime']]
        # if 'code' not in df.columns:
        #     df = df.reset_index()
        # if 'dt' in df.columns:
        #     df = df.drop(['dt'], axis=1)
        #     # df.dt = df.dt.astype(str)
        # if 'name' in df.columns:
        #     # df.name = df.name.astype(str)
        #     df = df.drop(['name'], axis=1)
        if 'code' not in df.columns:
            df = df.reset_index()
        if 'dt' in df.columns:
            df = df.drop(['dt'], axis=1)
            # df.dt = df.dt.astype(str)
        if 'name' in df.columns:
            df = df.drop(['name'], axis=1)
        if 'timel' in df.columns:
            df = df.drop(['timel'], axis=1)
            # df.name = df.name.astype(str)
        df = df.set_index(['code', 'ticktime'])
        # df = df.astype(float)
        # xcode = cct.code_to_symbol(code)
        # dd = pd.concat([dd, df], axis=0)
        # print df.loc[('600151')].index[-1]
        print((".", len(df)))
        # st.append(xcode,df)
        put_time = time.time()
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
        # print df
        # print df.shape
        # log.error("code :%s is None"%(code))
        time_s = time.time()
        h5a.write_hdf_db(h5_fname, df, table=h5_table, index=False, baseCount=500, append=False, MultiIndex=True)
        print(("hdf5 main all :%s  time:%0.2f" % (len(df), time.time() - time_s)))

        # print df[df.code == '600581']
        # print sina.get_stock_code_data('999999',index=True)
        # df = sina.get_stock_list_data(['600629', '000507']).set_index('code')
        # df = sina.get_stock_code_data('002775',index=False).set_index('code')
    # print df.loc['300380']
    # list=['000001','399001','399006','399005']
    # df=sina.get_stock_list_data(list)
    # print time.time() - times
    # print len(df.index)
    # print df[:4]
    # print df[df.code == '000024']
    # print df[df.code == '002788']
    # print df[df.code == '150027']
    # print df[df.code == '200024']
    # print df.code
    # print len(df.index)

    # print df[df.low.values <> df.high.values].iloc[:1,:8]
