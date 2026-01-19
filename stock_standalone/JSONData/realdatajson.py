#encoding: utf-8
"""
交易数据接口
Created on 2014/07/31
@author: Jimmy Liu
@group : waditu
@contact: jimmysoa@sina.cn
"""


import json
import math
import re
import sys
import time
import os
import pandas as pd
import asyncio
import random
# from pandas.compat import StringIO
# 而python2还是
# from StringIO import StringIO

sys.path.append("..")
import JohnsonUtil.johnson_cons as ct
from JohnsonUtil import LoggerFactory
# from JSONData.prettytable import *
from JohnsonUtil import commonTips as cct
from JSONData import tdx_hdf5_api as h5a

try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib.request import urlopen, Request

# log=LoggerFactory.getLogger('Realdata')
log = LoggerFactory.getLogger()
# log.setLevel(LoggerFactory.INFO)
# log=LoggerFactory.JohnsonLoger('Realdata')

sinaheader = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0',
    'Host': 'vip.stock.finance.sina.com.cn',
    'Referer':'http://vip.stock.finance.sina.com.cn',
    'Connection': 'keep-alive',
}

# sinaheader = {
#     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0',
#     'referer': 'http://finance.sina.com.cn',
#     'Connection': 'keep-alive',
# }

def _parsing_Market_price_json_src(url):
    """
           处理当日行情分页数据，格式为json
     Parameters
     ------
        pageNum:页码
     return
     -------
        DataFrame 当日所有股票交易数据(DataFrame)
    """
    # ct._write_console()
    # url="http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=50&sort=changepercent&asc=0&node=sh_a&symbol="
    # request = Request(ct.SINA_DAY_PRICE_URL%(ct.P_TYPE['http'], ct.DOMAINS['vsf'],
    #                              ct.PAGES['jv'], pageNum))
    # url='http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=20&sort=changepercent&asc=0&node=cyb&symbol='
    text = cct.get_url_data_R(url,headers=sinaheader)
    # text = cct.get_url_data(url)
    log.debug(f'url:{url},text:{text[:10]}')

    if text == 'null':
        return None
    elif text.find('IP') > 0:
        log.error("IP error:%s"%(text))
        return ''

    # text = text.replace('"{symbol', '{"symbol')
    # text = text.replace('{symbol', '{"symbol"')
    text = text.replace('changepercent', 'percent')
    text = text.replace('turnoverratio', 'ratio')
    # text.decode('unicode-escape')
    # js=json.loads(text,encoding='GBK')
    # df = pd.DataFrame(pd.read_json(js, dtype={'code':object}),columns=ct.MARKET_COLUMNS)
    js=json.loads(text)
    log.debug("Market json:%s count:%s"%(js[0],len(js)))
    df = pd.DataFrame(js,columns=ct.SINA_Market_COLUMNS)

    ### 20200422 problem : pd
    '''
    reg = re.compile(r'\,(.*?)\:')
    text = reg.sub(r',"\1":', text.decode('gbk') if ct.PY3 else text)
    text = text.replace('"{symbol', '{"symbol')
    text = text.replace('{symbol', '{"symbol"')
    text = text.replace('changepercent', 'percent')
    text = text.replace('turnoverratio', 'ratio')
    # print text
    if ct.PY3:
        jstr = json.dumps(text)
    else:
        # jstr = json.dumps(text, encoding='GBK')
        jstr = json.dumps(text,encoding='GBK')
    js = json.loads(jstr)
    # df = pd.DataFrame(pd.read_json(js, dtype={'code':object}),columns=ct.MARKET_COLUMNS)
    # log.debug("Market json:%s"%js[:1])
    df = pd.DataFrame(pd.read_json(js, dtype={'code': object}),
                      columns=ct.SINA_Market_COLUMNS)

    '''
    # df = df.drop('symbol', axis=1)
    df = df.loc[df.volume >= 0]
    # print type(df)
    # print df[-2:-1],len(df.index)
    # print df.loc['300208',['name']]
    return df


config_ini = cct.get_ramdisk_dir() + os.path.sep+ 'h5config.txt'
jsonfname = 'jsonlimit'
json_time = cct.get_config_value_wencai(config_ini,jsonfname,currvalue=time.time(),xtype='time',update=False)


def get_sina_Market_json_src(market='all', showtime=True, num='100', retry_count=3, pause=0.001):
    start_t = time.time()
#   qq stock api
#    http://qt.gtimg.cn/q=sz000858,sh600199
#    http://blog.csdn.net/ustbhacker/article/details/8365756
    # url="http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=50&sort=changepercent&asc=0&node=sh_a&symbol="
    # SINA_REAL_PRICE_DD = '%s%s/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=%s&sort=changepercent&asc=0&node=%s&symbol=%s'
    """
        一次性获取最近一个日交易日所有股票的交易数据
    return
    -------
      DataFrame
           属性：代码，名称，涨跌幅，现价，开盘价，最高价，最低价，最日收盘价，成交量，换手率
    """
    # ct._write_head()

    h5_fname = 'get_sina_all_ratio'
    # h5_table = 'all'
    h5_table = 'all'+'_'+str(num)
    # if market == 'all':
    limit_time = cct.sina_dd_limit_time
    h5 = h5a.load_hdf_db(h5_fname, table=h5_table,limit_time=limit_time)
    if h5 is not None and len(h5) > 0 and 'timel' in h5.columns:
        o_time = h5[h5.timel != 0].timel
        if len(h5) < 2000:
            log.error("h5 not full data")
            o_time = []
        if len(o_time) > 0:
            o_time = o_time[0]
            l_time = time.time() - o_time
            return_hdf_status = not cct.get_work_time() or (cct.get_work_time() and l_time < limit_time)
            if return_hdf_status:
                log.info("load hdf data:%s %s %s"%(h5_fname,h5_table,len(h5)))
                dd = None
                if market == 'all':
                    # co_inx = [inx for inx in h5.index if str(inx).startswith(('6','30','00','688','43','83','87','92'))]
                    co_inx = [inx for inx in h5.index if str(inx).startswith(cct.code_startswith)]
                elif market == 'sh':
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('6'))]
                elif market == 'sz':
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('00'))]
                elif market == 'cyb':
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('30'))]
                elif market == 'kcb':
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('688'))]
                elif market == 'bj':  
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('43','83','87','92'))]
                else:
                    log.error('market is not Find:%s'%(market))
                    codel = cct.read_to_blocknew(market)
                    co_inx = [inx for inx in codel if inx in h5.index]
                dd = h5.loc[co_inx]
                if len(dd) > 100:
                    log.info("return sina_ratio:%s"%(len(dd)))
                    return dd

    if h5 is None or market=='all':
        url_list=[]
        for m in ['sh_a','sz_a','hs_bjs']:
            mlist=_get_sina_Market_url(m, num=num)
            for l in mlist:url_list.append(l)
    else:
        url_list=_get_sina_Market_url(ct.SINA_Market_KEY[market], num=num)
    df = pd.DataFrame()
    # data['code'] = symbol
    # df = df.append(data, ignore_index=True)
    # results = cct.to_mp_run(_parsing_Market_price_json, url_list)
    # urltest ='http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=100&sort=changepercent&asc=0&node=sh_a&symbol='
    if len(url_list) > 0:
        log.debug("cct.to_asyncio_run:_parsing_Market_price_json:%s"%(url_list[0]))
        results = cct.to_asyncio_run(url_list, _parsing_Market_price_json)
    else:
        results = []
    if len(results)>0:

        df = pd.concat(results, ignore_index=True)
        if 'ratio' in df.columns:
            df['ratio']=df['ratio'].apply(lambda x:round(float(x),1))
        df['percent']=df['percent'].apply(lambda x:round(float(x),2))

    if df is not None and len(df) > 0:
        if 'code' in df.columns:
            df=df.drop_duplicates('code')
            df = df.set_index('code')
        if market=='all':
            h5 = h5a.write_hdf_db(h5_fname, df, table=h5_table,append=False)
        else:
            h5 = h5a.write_hdf_db(h5_fname, df, table=h5_table,append=True)
        if showtime: print(("Market-df:%s %s" % (format((time.time() - start_t), '.1f'), len(df))), end=' ')

        if market == 'all':
            co_inx = [inx for inx in df.index if str(inx).startswith(cct.code_startswith)]
            df = df.loc[co_inx]            
        elif market == 'sh':
            co_inx = [inx for inx in df.index if str(inx).startswith(('6'))]
            df = df.loc[co_inx]            
        elif market == 'sz':
            co_inx = [inx for inx in df.index if str(inx).startswith(('00'))]
            df = df.loc[co_inx]            
        elif market == 'cyb':
            co_inx = [inx for inx in df.index if str(inx).startswith(('30'))]
            df = df.loc[co_inx]            

        return df
    else:
        if showtime:print(("no data Market-df:%s" % (format((time.time() - start_t), '.2f'))))
        log.error("no data Market-df:%s"%(url_list[0]))
        return []


def get_base_path():
    """
    获取程序基准路径。在 Windows 打包环境 (Nuitka/PyInstaller) 中，
    使用 Win32 API 优先获取真实的 EXE 目录。
    """
    
    # 检查是否为 Python 解释器运行
    is_interpreter = os.path.basename(sys.executable).lower() in ('python.exe', 'pythonw.exe')
    
    # 1. 普通 Python 脚本模式
    if is_interpreter and not getattr(sys, "frozen", False):
        # 只有当它是 python.exe 运行 且 没有 frozen 标志时，才进入脚本模式
        try:
            # 此时 __file__ 是可靠的
            path = os.path.dirname(os.path.abspath(__file__))
            log.info(f"[DEBUG] Path Mode: Python Script (__file__). Path: {path}")
            return path
        except NameError:
             pass # 忽略交互模式
    
    # 2. Windows 打包模式 (Nuitka/PyInstaller EXE 模式)
    # 只要不是解释器运行，或者 sys.frozen 被设置，我们就认为是打包模式
    if sys.platform.startswith('win'):
        try:
            # 无论是否 Onefile，Win32 API 都会返回真实 EXE 路径
            real_path = cct._get_win32_exe_path()
            
            # 核心：确保我们返回的是 EXE 的真实目录
            if real_path != os.path.dirname(os.path.abspath(sys.executable)):
                 # 这是一个强烈信号：sys.executable 被欺骗了 (例如 Nuitka Onefile 启动器)，
                 # 或者程序被从其他地方调用，我们信任 Win32 API。
                 log.info(f"[DEBUG] Path Mode: WinAPI (Override). Path: {real_path}")
                 return real_path
            
            # 如果 Win32 API 结果与 sys.executable 目录一致，且我们处于打包状态
            if not is_interpreter:
                 log.info(f"[DEBUG] Path Mode: WinAPI (Standalone). Path: {real_path}")
                 return real_path

        except Exception:
            pass 

    # 3. 最终回退（适用于所有打包模式，包括 Linux/macOS）
    if getattr(sys, "frozen", False) or not is_interpreter:
        path = os.path.dirname(os.path.abspath(sys.executable))
        log.info(f"[DEBUG] Path Mode: Final Fallback. Path: {path}")
        return path

    # 4. 极端脚本回退
    log.info(f"[DEBUG] Path Mode: Final Script Fallback.")
    return os.path.dirname(os.path.abspath(sys.argv[0]))

BASE_DIR = get_base_path()

# --------------------------------------
# STOCK_CODE_PATH 专用逻辑
# --------------------------------------

def get_conf_path(fname):
    """
    获取并验证 stock_codes.conf

    逻辑：
      1. 优先使用 BASE_DIR/stock_codes.conf
      2. 不存在 → 从 JSONData/stock_codes.conf 释放
      3. 校验文件
    """
    # default_path = os.path.join(BASE_DIR, "stock_codes.conf")
    default_path = os.path.join(BASE_DIR, fname)

    # --- 1. 直接存在 ---
    if os.path.exists(default_path):
        if os.path.getsize(default_path) > 0:
            log.info(f"使用本地配置: {default_path}")
            return default_path
        else:
            log.warning("配置文件存在但为空，将尝试重新释放")

    # --- 2. 释放默认资源 ---
    cfg_file = cct.get_resource_file(
        rel_path=f"JSONData/{fname}",
        out_name=fname,
        BASE_DIR=BASE_DIR
    )

    # --- 3. 校验释放结果 ---
    if not cfg_file:
        log.error(f"获取 {fname} 失败（释放阶段）")
        return None

    if not os.path.exists(cfg_file):
        log.error(f"释放后文件仍不存在: {cfg_file}")
        return None

    if os.path.getsize(cfg_file) == 0:
        log.error(f"配置文件为空: {cfg_file}")
        return None

    log.info(f"使用内置释放配置: {cfg_file}")
    return cfg_file

from configobj import ConfigObj
import os
# http://www.cnblogs.com/qq78292959/archive/2013/07/25/3213939.html
def getconfigBigCount(count=None,write=False):

    # conf_ini = cct.get_work_path('stock','JSONData','count.ini')
    conf_ini= get_conf_path('count.ini')
    if not conf_ini:
        log.critical("scount.ini 加载失败，程序无法继续运行")
    fname = 'bigcount_logtime'
    logtime = cct.get_config_value_ramfile(fname)

    # print os.chdir(os.path.dirname(sys.argv[0]))
    # print (os.path.dirname(sys.argv[0]))
    # log.setLevel(LoggerFactory.INFO)
    if os.path.exists(conf_ini):
        log.info("file ok:%s"%conf_ini)
        config = ConfigObj(conf_ini,encoding='UTF8')
        if int(config['BigCount']['type2']) > 0:
            big_last= int(config['BigCount']['type2'])
            if logtime != 0:
                if (time.time() - float(cct.get_config_value_ramfile(fname)) > float(ct.bigcount_logtime)):
                    duratime = cct.get_config_value_ramfile(fname,currvalue=time.time(),xtype='time',update=True)
                    if count is None:
                        big_now = int(sina_json_Big_Count())
                    else:
                        big_now = int(count)
                else:
                    write = False
                    big_now = big_last
            else:
                duratime = cct.get_config_value_ramfile(fname,currvalue=time.time(),xtype='time',update=True)
                write = False
                big_now = big_last

            ratio_t=cct.get_work_time_ratio()
            bigRt=round( big_now / big_last / ratio_t, 1)
            big_v=int(bigRt*int(config['BigCount']['type2']))
            # print big_now,big_last,bigRt
            int_time=cct.get_now_time_int()
            # print int_time
            if write and (int_time < 915 or int_time > 1500 ) and big_now > 0 and big_last != big_now :
                # print write,not cct.get_work_time(),big_now > 0,big_last != big_now
                log.info("big_now update:%s last:%s"%(big_now,big_last))
                config['BigCount']['type2'] = big_now
                rt=float(config['BigCount']['ratio'])
                # if  rt != bigRt:
                log.info("bigRt:%s"%bigRt)
                config['BigCount']['ratio'] = bigRt
                config.write()
                return [big_now,bigRt,big_v]
            else:
                log.info("not work:%s ra:%s"%(big_now,bigRt))
                return [big_now,bigRt,big_v]
    else:
        config = ConfigObj(conf_ini,encoding='UTF8')
        config['BigCount'] = {}
        config['BigCount']['type2'] = sina_json_Big_Count()
        config['BigCount']['ratio'] = 0
        config.write()
    big_v= 0
    cl=[config['BigCount']['type2'],config['BigCount']['ratio'],0]
    return cl


def sina_json_Big_Count(vol='1', type='0', num='10000'):
    """[summary]

    [description]

    Parameters
    ----------
    vol : {str}, optional
        [description] (the default is '1', which [default_description])
    type : {str}, optional
        [description] (the default is '0', which [default_description])
    num : {str}, optional
        [description] (the default is '10000', which [default_description])

    Returns
    -------
    [type]
        [description]
    """
    url = ct.JSON_DD_CountURL % (ct.DD_VOL_List[vol], type)
    log.info("Big_Count_url:%s"%url)

    data = cct.get_url_data(url)
    
    count = re.findall('(\d+)', data, re.S)
    log.debug("Big_Count_count:%s"%count)
    if len(count) > 0:
        count = count[0]
    else:
        count = 0
    return count

def _get_sina_json_dd_url(vol='0', type='0', num='10000', count=None):
    urllist = []
    vol = str(vol)
    type = str(type)
    num = str(num)
    if count == None:
        url = ct.JSON_DD_CountURL % (ct.DD_VOL_List[vol], type)
        log.info("_json_dd_url:%s"%url)
        data = cct.get_url_data(url)
        # return []
        # print data.find('abc')
        count = re.findall('(\d+)', data, re.S)
        log.debug("_json_dd_url_count:%s"%count)
        # print count
        if len(count) > 0:
            count = count[0]
            bigcount=getconfigBigCount(count,write=False)
            print(("Big:%s V:%s "%(bigcount[0],bigcount[1])), end=' ')
            if int(count) >= int(num):
                page_count = int(math.ceil(int(count) / int(num)))
                for page in range(1, page_count + 1):
                    # print page
                    url = ct.JSON_DD_Data_URL_Page % (int(num), page, ct.DD_VOL_List[vol], type)
                    urllist.append(url)
            else:
                url = ct.JSON_DD_Data_URL_Page % (count, '1', ct.DD_VOL_List[vol], type)
                urllist.append(url)
        else:
            log.error("url Count error:%s count:%s"%(url,count))
            return []
    else:
        url = ct.JSON_DD_CountURL % (ct.DD_VOL_List[vol], type)
        # print url
        data = cct.get_url_data(url)
        # print data
        count_now = re.findall('(\d+)', data, re.S)
        urllist = []
        if count < count_now:
            count_diff = int(count_now) - int(count)
            if int(math.ceil(int(count_diff) / 10000)) >= 1:
                page_start = int(math.ceil(int(count) / 10000))
                page_end = int(math.ceil(int(count_now) / 10000))
                for page in range(page_start, page_end + 1):
                    # print page
                    url = ct.JSON_DD_Data_URL_Page % ('10000', page, ct.DD_VOL_List[vol], type)
                    urllist.append(url)
            else:
                page = int(math.ceil(int(count_now) / 10000))
                url = ct.JSON_DD_Data_URL_Page % ('10000', page, ct.DD_VOL_List[vol], type)
                urllist.append(url)
    # print "url:",urllist[:0]
    return urllist





def _parsing_sina_dd_price_json(url):
    """
           处理当日行情分页数据，格式为json
     Parameters
     ------
        pageNum:页码
     return
     -------
        DataFrame 当日所有股票交易数据(DataFrame)
    """
    ct._write_console()
    # request = Request(ct.SINA_DAY_PRICE_URL%(ct.P_TYPE['http'], ct.DOMAINS['vsf'],
    #                              ct.PAGES['jv'], pageNum))
    # request = Request(url)
    # text = urlopen(request, timeout=10).read()
    # sinaheader = {'Referer':'http://vip.stock.finance.sina.com.cn'}
    text = cct.get_url_data(url,headers=sinaheader)
    log.debug(f'url:{url}')
    # print(len(text))
    # return text
    if len(text) < 10 or text.find('finproduct@staff.sina.com.cn') > 0:
        return ''
    #2020 new json
    text = text.replace('symbol', 'code')
    # text = text.replace('turnoverratio', 'ratio')
    # text.decode('unicode-escape')
    # js=json.loads(text,encoding='GBK')
    js=json.loads(text)
    # df = pd.DataFrame(pd.read_json(js, dtype={'code':object}),columns=ct.MARKET_COLUMNS)
    log.debug("parsing_sina_dd:%s"%js[0])
    df = pd.DataFrame(js,columns=ct.DAY_REAL_DD_COLUMNS)
    #20200422 problem json
    '''
    reg = re.compile(r'\,(.*?)\:')
    text = reg.sub(r',"\1":', text.decode('gbk') if ct.PY3 else text)
    text = text.replace('"{symbol', '{"code')
    text = text.replace('{symbol', '{"code"')

    if ct.PY3:
        jstr = json.dumps(text)
    else:
        # jstr = json.dumps(text, encoding='GBK')
        jstr = json.dumps(text)
    js = json.loads(jstr)
    df = pd.DataFrame(pd.read_json(js, dtype={'code': object}),
                      columns=ct.DAY_REAL_DD_COLUMNS)
    '''
    df = df.drop('symbol', axis=1)
    df = df.loc[df.volume > '0']
    # print df['name'][len(df.index)-1:],len(df.index)
    return df

# data = cct.to_mp_run(_parsing_sina_dd_price_json, url_list)
    # data = cct.to_mp_run_async(_parsing_sina_dd_price_json, url_list)

    # if len(url_list)>cct.get_cpu_count():
    #     divs=cct.get_cpu_count()
    # else:
    #     divs=len(url_list)
    #
    # if len(url_list)>=divs:
    #     print len(url_list),
    #     dl=cct.get_div_list(url_list,divs)
    #     data=cct.to_mp_run_async(cct.to_asyncio_run,dl,_parsing_sina_dd_price_json)
    # else:
    #     data=cct.to_asyncio_run(url_list,_parsing_sina_dd_price_json)



        # data = cct.to_asyncio_run(url_list, _parsing_sina_dd_price_json)  //return df list 
        # if len(data)>50:
        #     df = df.append(data, ignore_index=True)
        #     # log.debug("dd.columns:%s" % df.columns.values)
        #     #['code' 'name' 'ticktime' 'price' 'volume' 'prev_price' 'kind']
        #     log.debug("get_sina_all_json_dd:%s" % df[:1])


async def _fetch_with_dd_delay(url, pause_range):
    now = time.time()
    if now < g_sina_blocked['blocked_until']:
        wait = g_sina_blocked['blocked_until'] - now
        log.warning(f"[SINA-WAIT] {wait:.1f}s")
        await asyncio.sleep(wait)

    try:
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, _parsing_sina_dd_price_json, url)
        if df is None or len(df) == 0:
            df = None
        # else:
        #     log.error(f"_parsing_sina_dd_price_json is Null : {url}")
        #     return None
    except Exception as e:
        log.error(f"Fetch url error: {url}, {e}")
        # 触发冷却模式
        set_blocked_cooling(reason=str(e), factor=1.23, cooling_sec=300)
        df = None
        set_blocked(60, str(e), url)
        return None

    sleep_t = random.uniform(*pause_range)
    await asyncio.sleep(sleep_t)
    return df

async def _fetch_parsed(url):
    """
    异步抓取并解析单个 url  gpt 没用
    """
    dd_l = await _parsing_sina_dd_price_json(url)  # 假设原来的解析函数可改成 async
    if dd_l is not None and len(dd_l) > 2:
        return dd_l
    else:
        log.error(f"_parsing_sina_dd_price_json is Null : {url}")
        return None

def get_sina_all_json_dd(vol='0', type='0', num='10000', retry_count=3, pause=0.001,batch_size=5, pause_range=(0.2, 0.8)):
    start_t = time.time()
    # url="http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=50&sort=changepercent&asc=0&node=sh_a&symbol="
    # SINA_REAL_PRICE_DD = '%s%s/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=%s&sort=changepercent&asc=0&node=%s&symbol=%s'
    #http://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill_sum.php
    #http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_Bill.GetBillList?num=10000&page=1&sort=ticktime&asc=0&volume=100000&type=0
    #http://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill_all.php?num=100&page=1&sort=ticktime&asc=0&volume=100000&type=0
    """
        一次性获取最近一个日交易日所有股票的交易数据
    return
    -------
      DataFrame
           属性：代码，名称，涨跌幅，现价，开盘价，最高价，最低价，最日收盘价，成交量，换手率
    """
    # return ''
    h5_fname = 'get_sina_all_dd'
    h5_table = 'all'+'_'+ct.DD_VOL_List[str(vol)]+'_'+str(num)
    # limit_time = cct.sina_dd_limit_time
    base_limit = cct.sina_dd_limit_time

    batch_size, pause_range, force_cache, limit_time = _get_dynamic_fetch_params(
        batch_size, pause_range, base_limit
    )

    h5 = h5a.load_hdf_db(h5_fname, table=h5_table,limit_time=limit_time)
    if h5 is not None and not h5.empty and len(h5) > 100 and 'timel' in h5.columns:
       o_time = h5[h5.timel != 0].timel
       if len(o_time) > 0:
           o_time = o_time[0]
           l_time = time.time() - o_time
           log.info(f'limit_time : {limit_time} l_time : {l_time}')
           return_hdf_status = not cct.get_work_time() or (cct.get_work_time() and l_time < limit_time)
           if return_hdf_status:
               log.info("load hdf data:%s %s %s"%(h5_fname,h5_table,len(h5)))
               return h5
    log.info(f'limit_time:{limit_time}')
    url_list = _get_sina_json_dd_url(vol, type, num)
    df = pd.DataFrame()
    if not url_list:
        print(f"Url None json-df:{time.time() - start_t:.2f}")
        return ''

    df_list = []
    loop = asyncio.get_event_loop()

    for i in range(0, len(url_list), batch_size):
        log.debug(f"Processing batch {i//batch_size + 1} / {len(url_list)//batch_size + 1}")
        tasks = [_fetch_with_dd_delay(u,pause_range) for u in url_list[i:i+batch_size]]
        try:
            rs = loop.run_until_complete(asyncio.gather(*tasks))
            log.debug(f"Batch {i//batch_size + 1} completed")
        except Exception as e:
            set_blocked(120, f"batch error:{e}")
            break

        for r in rs:
            if r is not None and not r.empty:
                df_list.append(r)

    if not df_list:
        log.error("no data fetched")
        return []

    df = pd.concat(df_list, ignore_index=True)
    
    if len(df) > 50:
        time_drop = time.time()
        df['couts'] = df.groupby('code')['code'].transform('count')
        df = df.sort_values(by='couts', ascending=False)
        df = df.drop_duplicates('code')
        print(f"djdf:{time.time()-time_drop:.1f}", end=' ')
        log.info(f"sina-DD:{df[:1]}")
        df = df.loc[:, ['code','name','couts','kind','prev_price','ticktime']]
        df['code'] = df['code'].apply(lambda x: str(x).replace('sh','') if str(x).startswith('sh') else str(x).replace('sz',''))
        if len(df) > 0:
            df = df.set_index('code')
            h5 = h5a.write_hdf_db(h5_fname, df, table=h5_table, append=False)
            log.info(f"get_sina_all_json_dd:{len(df)}")
        print(f" dd-df:{time.time()-start_t:.2f}", end=' ')
        return df
    else:
        print(f"url:{url_list[0]} no data  json-df:{time.time()-start_t:.2f}", end=' ')
        return ''

def get_sina_all_json_dd_old_2026(vol='0', type='0', num='10000', retry_count=3, pause=0.001):
    start_t = time.time()
    # url="http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=50&sort=changepercent&asc=0&node=sh_a&symbol="
    # SINA_REAL_PRICE_DD = '%s%s/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=%s&sort=changepercent&asc=0&node=%s&symbol=%s'
    #http://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill_sum.php
    #http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_Bill.GetBillList?num=10000&page=1&sort=ticktime&asc=0&volume=100000&type=0
    #http://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill_all.php?num=100&page=1&sort=ticktime&asc=0&volume=100000&type=0
    """
        一次性获取最近一个日交易日所有股票的交易数据
    return
    -------
      DataFrame
           属性：代码，名称，涨跌幅，现价，开盘价，最高价，最低价，最日收盘价，成交量，换手率
    """
    # return ''
    h5_fname = 'get_sina_all_dd'
    h5_table = 'all'+'_'+ct.DD_VOL_List[str(vol)]+'_'+str(num)
    limit_time = cct.sina_dd_limit_time
    h5 = h5a.load_hdf_db(h5_fname, table=h5_table,limit_time=limit_time)
    if h5 is not None and not h5.empty and len(h5) > 100 and 'timel' in h5.columns:
       o_time = h5[h5.timel != 0].timel
       if len(o_time) > 0:
           o_time = o_time[0]
           l_time = time.time() - o_time
           log.info(f'limit_time : {limit_time} l_time : {l_time}')
           return_hdf_status = not cct.get_work_time() or (cct.get_work_time() and l_time < limit_time)
           if return_hdf_status:
               log.info("load hdf data:%s %s %s"%(h5_fname,h5_table,len(h5)))
               return h5
    log.info(f'limit_time:{limit_time}')
    url_list = _get_sina_json_dd_url(vol, type, num)
    df = pd.DataFrame()
    if len(url_list)>0:
        log.info("json_dd_url:%s"%url_list[0])
        for url in url_list:
            dd_l = _parsing_sina_dd_price_json(url)
            if len(dd_l) > 2:
                df = pd.concat([df,dd_l])
            else:
                log.error("_parsing_sina_dd_price_json is Null :%s"%(dd_l))
        if df is not None and not df.empty and len(df) > 50:
            time_drop=time.time()
            df['couts']=df.groupby(['code'])['code'].transform('count')
            df=df.sort_values(by='couts',ascending=0)
            df=df.drop_duplicates('code')
            print("djdf:%0.1f"%(time.time()-time_drop), end=' ')
            log.info("sina-DD:%s" % df[:1])
            df = df.loc[:, ['code','name', 'couts', 'kind', 'prev_price','ticktime']]
            df.code=df.code.apply(lambda x:str(x).replace('sh','') if str(x).startswith('sh') else str(x).replace('sz',''))
            if len(df) > 0:
                df = df.set_index('code')
                h5 = h5a.write_hdf_db(h5_fname, df, table=h5_table,append=False)
                log.info("get_sina_all_json_dd:%s"%(len(df)))
            print((" dd-df:%0.2f" % ((time.time() - start_t))), end=' ')
            return df
        else:
            print()
            print(("url:%s no data  json-df:%0.2f"%(url_list[0],(time.time() - start_t))), end=' ')
            return ''
    else:
        print(("Url None json-df:%0.2f "%((time.time() - start_t))), end=' ')
        return ''


def _get_index_url(index, code, qt):
    if index:
        url = ct.HIST_INDEX_URL % (ct.P_TYPE['http'], ct.DOMAINS['vsf'],
                                   code, qt[0], qt[1])
    else:
        url = ct.HIST_FQ_URL % (ct.P_TYPE['http'], ct.DOMAINS['vsf'],
                                code, qt[0], qt[1])
    return url


def _get_hists(symbols, start=None, end=None,
               ktype='D', retry_count=3,
               pause=0.001):
    """
    批量获取历史行情数据，具体参数和返回数据类型请参考get_hist_data接口
    """
    df = pd.DataFrame()
    if isinstance(symbols, list) or isinstance(symbols, set) or isinstance(symbols, tuple) or isinstance(symbols,
                                                                                                         pd.Series):
        for symbol in symbols:
            data = get_hist_data(symbol, start=start, end=end,
                                 ktype=ktype, retry_count=retry_count,
                                 pause=pause)
            data['code'] = symbol
            df = pd.concat(data, ignore_index=True)
        return df
    else:
        return None

def get_sina_dd_count_price_realTime(df='',table='all',vol='0',type='0'):
    '''
    input df count and merge price to df
    '''
#    if table <> 'all':
#        log.error("check market is not all")

    if len(df)==0:
        # df = get_sina_all_json_dd('0')
        df = get_sina_all_json_dd(vol,type)

    if len(df)>0:
        df['couts']=df.groupby(['code'])['code'].transform('count')
        # df=df[(df['kind'] == 'U')]
        df=df.sort_values(by='couts',ascending=0)
        time_drop=time.time()
        df=df.drop_duplicates('code')
        print("ddf:%0.1f"%(time.time()-time_drop), end=' ')
        # df=df[df.price >df.prev_price]
        df = df.loc[:, ['code', 'name', 'couts', 'prev_price']]
        log.info("df.market:%s" % df[:1])

        # dz.loc['sh600110','couts']=dz.loc['sh600110'].values[1]+3
        df=df.set_index('code')
        # df=df.iloc[0:,0:2]
        df['dff']=0

        dp=get_sina_Market_json(table)
        log.info("dp.market:%s" % dp[:1])
        if len(dp)>10:
            dp=dp.dropna()
            time_drop=time.time()
            dp=dp.drop_duplicates('code')
            print("ddp:%0.1f"%(time.time()-time_drop), end=' ')
            log.info("dp to dm.market:%s" % dp[:1])
            dm=pd.merge(df,dp,on='name',how='left')
            # dm=dm.drop_duplicates('code')
            dm=dm.set_index('code')
            dm=dm.dropna('index')
            log.info("dm.market2:%s" % dm[:1])
            # dm.loc[dm.percent>9.9,'percent']=10
            # print dm[-1:]
            dm=dm.loc[:,ct.SINA_DD_Clean_Count_Columns]
            dm.prev_price=dm.prev_price.fillna(0.0)
            dm.rename(columns={'prev_price': 'prev_p'}, inplace=True)

            # print dm[-1:]
        else:
            dm=df
    else:
        dm=''
    return dm
def get_sina_tick_js_LastPrice(symbols):
    symbols_list=''
    if len(symbols) == 0:
        return ''
    if isinstance(symbols, list) or isinstance(symbols, set) or isinstance(symbols, tuple) or isinstance(symbols, pd.Series):
        for code in symbols:
            symbols_list += cct.code_to_symbol(code) + ','
    else:
        symbols_list = cct.code_to_symbol(symbols)
    # print symbol_str
    url="http://hq.sinajs.cn/list=%s"%(symbols_list)
    # print url
    data = cct.get_url_data(url)
    # vollist=re.findall('{data:(\d+)',code)
    # print data
    ulist=data.split(";")
    price_dict={}
    for var in range(0,len(ulist)-1):
        # print var
        if len(ulist)==2:
            code=symbols
        else:
            code=symbols[var]
        tempData = re.search('''(")(.+)(")''', ulist[var]).group(2)
        stockInfo = tempData.split(",")
        # stockName   = stockInfo[0]  #名称
        # stockStart  = stockInfo[1]  #开盘
        stockLastEnd= stockInfo[2]  #昨收盘
        # stockCur    = stockInfo[3]  #当前
        # stockMax    = stockInfo[4]  #最高
        # stockMin    = stockInfo[5]  #最低
        # price_dict[code]=stockLastEnd
        price_dict[code]=float(stockLastEnd)

        # stockUp     = round(float(stockCur) - float(stockLastEnd), 2)
        # stockRange  = round(float(stockUp) / float(stockLastEnd), 4) * 100
        # stockVolume = round(float(stockInfo[8]) / (100 * 10000), 2)
        # stockMoney  = round(float(stockInfo[9]) / (100000000), 2)
        # stockTime   = stockInfo[31]
        # dd={}
    return price_dict


def get_market_LastPrice_sina_js(codeList):
    # time_s=time.time()
    if isinstance(codeList, list) or isinstance(codeList, set) or isinstance(codeList, tuple) or isinstance(codeList, pd.Series):
        if len(codeList)>200:
            # num=int(len(codeList)/cpu_count())
            div_list = cct.get_div_list(codeList, 100)
            # print "ti:",time.time()-time_s
            results = cct.to_mp_run(get_sina_tick_js_LastPrice, div_list)
            # print results
        else:
            results=get_sina_tick_js_LastPrice(codeList)
        # print "time:",time.time()-time_s
        return results
    else:
        print("codeL not list")
        # return get_sina_tick_js_LastPrice(codeList)


def get_market_price_sina_dd_realTime(dp='',vol='0',type='0'):
    '''
    input df count and merge price to df
    '''
    if len(dp)==0:
        dp=get_sina_Market_json()
    if len(dp)>0:
        log.info("Market_realTime:%s"%len(dp))
        dp=dp.fillna(0)
        dp=dp.dropna()
        log.info("DP:%s" % dp[:1].open)
        dp['dff']=0
        df=get_sina_all_json_dd(vol,type)

        if len(df)>0:
            dm = cct.combine_dataFrame(dp,df)
            log.info("top_now:main:%s subobject:%s dm:%s "%(len(dp),len(df),len(dm)))
            log.debug("dmMerge:%s"%dm.columns[:5])
            dm.couts=dm.couts.fillna(0)
            dm.prev_price=dm.prev_price.fillna(0.0)
            dm.couts=dm.couts.astype(int)
            dm.rename(columns={'prev_price': 'prev_p'}, inplace=True)
        else:
            if len(dp) > 0:
                if 'code' in dp.columns:dp=dp.set_index('code')
                dp['couts'] = 0
                dp['prev_p'] = 0
                dm = dp
            else:
                log.error('dp is None')
                dm = ''

    else:
        dm=''
    # print type(dm)

    return dm


# =========================
# Sina Header
# =========================
sinaheader = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0',
    'Host': 'vip.stock.finance.sina.com.cn',
    'Referer': 'http://vip.stock.finance.sina.com.cn',
    'Connection': 'keep-alive',
}

# =========================
# 全局封禁状态（增强）
# =========================
g_sina_blocked = {
    'last_block_time': 0,
    'last_url': '',
    'blocked_until': 0,   # 封禁结束时间
    'reason': '',         # 封禁原因
    'count': 0,           # 连续封禁次数
    'cooling': False      # 是否在冷却模式
}


def set_blocked(seconds, reason='', url=''):
    now = time.time()
    g_sina_blocked['count'] += 1
    g_sina_blocked['last_block_time'] = now
    g_sina_blocked['reason'] = reason
    g_sina_blocked['last_url'] = url

    penalty = min(seconds * (1 + g_sina_blocked['count'] * 0.5), 600)
    g_sina_blocked['blocked_until'] = now + penalty

    log.warning(
        f"[SINA-BLOCK] count={g_sina_blocked['count']} "
        f"penalty={penalty:.1f}s reason={reason} url={url}"
    )

def set_blocked_cooling(reason='', factor=1.23, cooling_sec=300):
    """
    触发冷却模式：
    - limit_time 按 factor 放大
    - 当天禁止递减
    - 冷却时间 cooling_sec 秒
    """
    now = time.time()
    g_sina_blocked['blocked_until'] = now + cooling_sec
    g_sina_blocked['reason'] = reason
    g_sina_blocked['count'] += 1
    g_sina_blocked['cooling'] = True

    # 调整 limit_time
    if hasattr(cct, "sina_dd_limit_time"):
        new_limit = int(cct.sina_dd_limit_time * factor)
        cct.sina_dd_limit_time = new_limit
        log.warning(f"[SINA-COOLING] Triggered due to {reason}, "
                    f"limit_time increased: {new_limit}s, cooling for {cooling_sec}s")


# =========================
# 动态参数计算（功能 3 + 4）
# =========================
def _get_dynamic_fetch_params_increase(base_batch, base_pause, base_limit):
    #尽量使用limit,直到封禁
    is_trade = cct.get_work_time()
    block_cnt = g_sina_blocked['count']

    # batch_size
    if is_trade:
        batch_size = max(5, int(base_batch * 0.4))
    else:
        batch_size = base_batch

    if block_cnt > 0:
        batch_size = max(3, int(batch_size / (1 + block_cnt * 0.7)))

    # pause
    slow = 1 + block_cnt * 0.5
    pause_range = (
        round(base_pause[0] * slow, 2),
        round(base_pause[1] * slow + 0.3, 2)
    )

    # limit_time 联动
    force_cache = False
    limit_time = base_limit
    if block_cnt >= 2:
        limit_time = base_limit * (1 + block_cnt)
        force_cache = True

    return batch_size, pause_range, force_cache, limit_time

def _get_dynamic_fetch_params_noCoolTime(base_batch, base_pause, base_limit):
    """
    反向优化版：
    - base_limit 是当前“已验证安全”的缓存时间
    - 动态逻辑只允许【缩短】limit_time
    - 一旦异常，立即回退到 base_limit
    """

    is_trade = cct.get_work_time()
    block_cnt = g_sina_blocked['count']

    # =========================
    # batch_size（仍然保守）
    # =========================
    if is_trade:
        batch_size = max(5, int(base_batch * 0.4))
    else:
        batch_size = base_batch

    if block_cnt > 0:
        batch_size = max(3, int(batch_size / (1 + block_cnt * 0.7)))

    # =========================
    # pause（随封禁递增）
    # =========================
    slow = 1 + block_cnt * 0.5
    pause_range = (
        round(base_pause[0] * slow, 2),
        round(base_pause[1] * slow + 0.3, 2)
    )

    # =========================
    # limit_time：倒序缩减
    # =========================
    force_cache = False
    limit_time = base_limit

    if block_cnt >= 2:
        # 🚨 连续异常：冻结策略
        force_cache = True
        limit_time = base_limit

    elif block_cnt == 1:
        # ⚠️ 出现一次异常：不尝试缩减
        limit_time = base_limit

    else:
        # ✅ 完全正常，允许尝试缩减
        if is_trade:
            # 交易时间极保守
            shrink_factor = 0.85
        else:
            # 非交易时间可激进一些
            shrink_factor = 0.65

        limit_time = max(
            int(base_limit * shrink_factor),
            int(base_limit * 0.3)   # 下限保护，防止过快
        )

    return batch_size, pause_range, force_cache, limit_time

def _get_dynamic_fetch_params(base_batch, base_pause, base_limit):
    """
    反向优化版 + 冷却模式：
    - base_limit 是当前“已验证安全”的缓存时间
    - 异常触发冷却 -> limit_time 按系数增长
    - 正常 -> 倒序缩减
    """

    is_trade = cct.get_work_time()
    block_cnt = g_sina_blocked.get('count', 0)

    # =========================
    # 冷却模式优先
    # =========================
    if g_sina_blocked.get('cooling', False):
        batch_size = max(3, int(base_batch * 0.3))
        pause_range = (0.8, 1.2)
        force_cache = True
        limit_time = cct.sina_dd_limit_time  # 放大后的冷却值
        return batch_size, pause_range, force_cache, limit_time

    # =========================
    # batch_size（仍然保守）
    # =========================
    if is_trade:
        batch_size = max(5, int(base_batch * 0.4))
    else:
        batch_size = base_batch

    if block_cnt > 0:
        batch_size = max(3, int(batch_size / (1 + block_cnt * 0.7)))

    # =========================
    # pause（随封禁递增）
    # =========================
    slow = 1 + block_cnt * 0.5
    pause_range = (
        round(base_pause[0] * slow, 2),
        round(base_pause[1] * slow + 0.3, 2)
    )

    # =========================
    # limit_time：倒序缩减
    # =========================
    force_cache = False
    limit_time = base_limit

    if block_cnt >= 2:
        # 🚨 连续异常：冻结策略
        force_cache = True
        limit_time = base_limit

    elif block_cnt == 1:
        # ⚠️ 出现一次异常：不尝试缩减
        limit_time = base_limit

    else:
        # ✅ 完全正常，允许尝试缩减
        shrink_factor = 0.9 if is_trade else 0.65
        limit_time = max(int(base_limit * shrink_factor), int(base_limit * 0.3))
    if not cct.get_work_time():
        force_cache = True
    return batch_size, pause_range, force_cache, limit_time

# =========================
# URL 构建
# =========================
def _get_sina_Market_url(market='sh_a', num='200'):
    url_list = []
    url = ct.JSON_Market_Center_CountURL % market
    data = cct.get_url_data(url, timeout=10)
    cnt = re.findall('(\d+)', data or '')
    if cnt:
        page_cnt = max(1, -(-int(cnt[0]) // int(num)))
        for p in range(1, page_cnt + 1):
            url_list.append(ct.JSON_Market_Center_RealURL % (p, num, market))
    return url_list


# =========================
# 数据解析（强风控识别）
# =========================
def _parsing_Market_price_json(url):
    text = cct.get_url_data_R(url, headers=sinaheader)
    if not text:
        raise ValueError("empty response")
    if text in ('null', 'None') or text.startswith('<html'):
        raise ValueError("blocked html/null")

    try:
        text = text.replace('changepercent', 'percent').replace('turnoverratio', 'ratio')
        js = json.loads(text)
    except Exception:
        raise ValueError("json decode failed")

    df = pd.DataFrame(js, columns=ct.SINA_Market_COLUMNS)
    df = df.loc[df.volume >= 0]
    if df.empty:
        raise ValueError("empty dataframe")

    return df


# =========================
# 异步抓取（自适应节流）
# =========================
async def _fetch_with_delay(url, pause_range):
    now = time.time()
    if now < g_sina_blocked['blocked_until']:
        wait = g_sina_blocked['blocked_until'] - now
        log.warning(f"[SINA-WAIT] {wait:.1f}s")
        await asyncio.sleep(wait)

    try:
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, _parsing_Market_price_json, url)
    except Exception as e:
        log.error(f"Fetch url error: {url}, {e}")
        # 触发冷却模式
        set_blocked_cooling(reason=str(e), factor=1.23, cooling_sec=300)
        df = None
        set_blocked(60, str(e), url)
        return None

    sleep_t = random.uniform(*pause_range)
    await asyncio.sleep(sleep_t)
    return df

def _can_update_limit_time_base(base_limit, limit_time):
    """
    判断是否满足写回 global.ini 的条件
    """
    # 时间条件
    now = time.localtime()
    if not (now.tm_hour == 14 and now.tm_min >= 50 or now.tm_hour > 14):
        return False

    # 必须真的缩小了
    if limit_time >= base_limit:
        return False

    # 当天必须没有被封
    if g_sina_blocked['count'] > 0:
        return False

    # 防止极端缩减
    if limit_time < int(base_limit * 0.3):
        return False

    return True


def _can_update_limit_time(
    base_limit,
    limit_time,
    min_sample_sec=10800,    # 至少 15 分钟安全样本
):
    """
    判断是否允许将 limit_time 写回 global.ini
    条件：
    1. 每天只允许写一次
    2. 当天必须无封禁
    3. 必须有足够安全运行样本
    4. 只允许 14:50 ~ 15:00 窗口
    5. limit_time 必须真实缩小
    """

    now = time.localtime()

    # ========= 时间窗口限制 =========
    # 14:50 <= time < 15:00
    if not (
        (now.tm_hour == 14 and now.tm_min >= 50) or
        (now.tm_hour == 15 and now.tm_min == 0)
    ):
        return False

    # 15:00 之后禁止
    if now.tm_hour >= 15 and now.tm_min > 0:
        return False

    # ========= 必须真实缩小 =========
    if limit_time >= base_limit:
        return False

    # ========= 当天不能被封 =========
    if g_sina_blocked.get('count', 0) > 0:
        return False

    # ========= 最小安全样本 =========
    # 使用首次成功获取时间作为样本起点
    first_ok_ts = getattr(cct, '_sina_first_ok_ts', None)
    if not first_ok_ts:
        return False

    if time.time() - first_ok_ts < min_sample_sec:
        return False

    # ========= 每天只写一次 =========
    today = time.strftime("%Y%m%d", now)

    # last_write_day = cct.CFG.get("general","sina_dd_limit_day",fallback="")
    last_write_day = cct.CFG.get_with_writeback(
        section="general",
        option="sina_dd_limit_day",
        fallback="0",       # 默认是 0，表示未写
        value_type="str"
        )

    if last_write_day == today:
        return False

    return True

def _update_sina_limit_time(limit_time):
    """
    写入 global.ini，并同步更新 cct.sina_dd_limit_time（内存态）
    """
    try:
        limit_time = int(limit_time)
        cct.CFG.set_and_save(
            section="general",
            key="sina_dd_limit_time",
            value=limit_time
        )

        # 🔑 同步模块级缓存值（关键）
        cct.sina_dd_limit_time = limit_time
        today = time.strftime("%Y%m%d")
        cct.CFG.set_and_save(
            section="general",
            key="sina_dd_limit_day",
            value=today
        )
        log.warning(
            f"[SINA-LIMIT-UPDATE] sina_dd_limit_time={limit_time}"
        )
        return True

    except Exception as e:
        log.error(f"[SINA-LIMIT-UPDATE-FAIL] {e}")
        return False

# =========================
# 主入口（完整优化版）
# =========================
def get_sina_Market_json(market='all', showtime=True, num='100', retry_count=3, pause=0.001,batch_size=50, pause_range=(0.2, 0.8)):
    start = time.time()
    h5_fname = 'get_sina_all_ratio'
    h5_table = f'all_{num}'
    base_limit = cct.sina_dd_limit_time

    batch_size, pause_range, force_cache, limit_time = _get_dynamic_fetch_params(
        batch_size, pause_range, base_limit
    )

    log.info(f'batch_size:{batch_size} pause_range:{pause_range} force_cache:{force_cache} limit_time:{limit_time} base_limit:{base_limit}')
    # --------- HDF 缓存 ---------
    h5 = h5a.load_hdf_db(h5_fname, table=h5_table, limit_time=limit_time)
    if h5 is not None and len(h5) > 0 and 'timel' in h5.columns:
        o_time = h5[h5.timel != 0].timel
        if len(o_time) > 0:
            l_time = time.time() - o_time.iloc[0]
            if force_cache or l_time < limit_time:
                log.warning(f"[HDF-USE] rows={len(h5)} l_time={l_time:.1f}")
                if market == 'all':
                    # co_inx = [inx for inx in h5.index if str(inx).startswith(('6','30','00','688','43','83','87','92'))]
                    co_inx = [inx for inx in h5.index if str(inx).startswith(cct.code_startswith)]
                elif market == 'sh':
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('6'))]
                elif market == 'sz':
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('00'))]
                elif market == 'cyb':
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('30'))]
                elif market == 'kcb':
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('688'))]
                elif market == 'bj':  
                #elem.startswith('43') or elem.startswith('83') or elem.startswith('87') or elem.startswith('92')
                    co_inx = [inx for inx in h5.index if str(inx).startswith(('43','83','87','92'))]
                else:
                    log.error('market is not Find:%s'%(market))
                    codel = cct.read_to_blocknew(market)
                    co_inx = [inx for inx in codel if inx in h5.index]
                dd = h5.loc[co_inx]
                if len(dd) > 100:
                    log.info(f"return sina_ratio market:{market} count:{len(dd)}")
                    return dd

    # --------- URL 构建 ---------
    url_list = []
    # SINA_Market_KEY = {'sh': 'sh_a', 'sz': 'sz_a', 'cyb': 'cyb','kcb':'kcb','bj':'hs_bjs'}
    if market == 'all':
        for m in ('sh_a', 'sz_a' , 'hs_bjs'):
            url_list.extend(_get_sina_Market_url(m, num))
    else:
        url_list = _get_sina_Market_url(ct.SINA_Market_KEY.get(market, market), num)

    if not url_list:
        log.error("no url list")
        return []

    log.info(
        f"[SINA-FETCH] urls={len(url_list)} batch={batch_size} "
        f"pause={pause_range} block={g_sina_blocked['count']}"
    )

    df_list = []
    loop = asyncio.get_event_loop()
    total_batches = (len(url_list) + batch_size - 1) // batch_size

    for i in range(0, len(url_list), batch_size):
        batch_num = i // batch_size + 1
        log.info(f"[SINA-进度] 批次 {batch_num}/{total_batches} 开始... (已获取 {len(df_list)} 个结果)")
        tasks = [_fetch_with_delay(u, pause_range) for u in url_list[i:i + batch_size]]
        try:
            rs = loop.run_until_complete(asyncio.gather(*tasks))
            log.info(f"[SINA-进度] 批次 {batch_num}/{total_batches} 完成 ✓")
        except Exception as e:
            set_blocked(120, f"batch error:{e}")
            break

        for r in rs:
            if r is not None and not r.empty:
                df_list.append(r)

    if not df_list:
        log.error("no data fetched")
        return []

    df = pd.concat(df_list, ignore_index=True)
    if 'ratio' in df.columns:
        df['ratio'] = df['ratio'].astype(float).round(1)
    if 'percent' in df.columns:
        df['percent'] = df['percent'].astype(float).round(2)
    df = df.drop_duplicates('code').set_index('code')

    if df is not None and len(df) > 0:
        if 'code' in df.columns:
            df = df.drop_duplicates('code').set_index('code')
        if market=='all':
            h5 = h5a.write_hdf_db(h5_fname, df, table=h5_table,append=False)
        else:
            h5 = h5a.write_hdf_db(h5_fname, df, table=h5_table,append=True)
        # if showtime: print(("Market-df:%s %s" % (format((time.time() - start_t), '.1f'), len(df))), end=' ')
        if market == 'all':
            co_inx = [inx for inx in df.index if str(inx).startswith(('6','30','00','688','43','83','87','92'))]
            df = df.loc[co_inx]            
        elif market == 'sh':
            co_inx = [inx for inx in df.index if str(inx).startswith(('6'))]
            df = df.loc[co_inx]            
        elif market == 'sz':
            co_inx = [inx for inx in df.index if str(inx).startswith(('00'))]
            df = df.loc[co_inx]            
        elif market == 'cyb':
            co_inx = [inx for inx in df.index if str(inx).startswith(('30'))]
            df = df.loc[co_inx]            
        elif market == 'kcb':
            co_inx = [inx for inx in df.index if str(inx).startswith(('688'))]
            df = df.loc[co_inx]  
        elif market == 'bj':  
            co_inx = [inx for inx in df.index if str(inx).startswith(('43','83','87','92'))]
            df = df.loc[co_inx]
        else:
            log.error('market is not Find:%s'%(market))
            codel = cct.read_to_blocknew(market)
            co_inx = [inx for inx in codel if inx in df.index]
            df = df.loc[co_inx]
        log.info(f"return sina_ratio market:{market} count:{len(df)}")

    else:
        if showtime:print(("no data Market-df:%s" % (format((time.time() - start_t), '.2f'))))
        log.error("no data Market-df:%s"%(url_list[0]))
        return []

    if showtime:
        print(f"Market-df:{time.time() - start:.1f}s {len(df)}", end=' ')

    # =========================
    # 14:50 后自动收敛 limit_time
    # =========================
    if not hasattr(cct, "_sina_first_ok_ts"):
        cct._sina_first_ok_ts = time.time()
    if _can_update_limit_time(base_limit, limit_time):
        log.warning(
            f"[SINA-LIMIT-CANDIDATE] base={base_limit} new={limit_time}"
        )
        _update_sina_limit_time(limit_time)

    return df



if __name__ == '__main__':
    import sys
    # log.setLevel(LoggerFactory.DEBUG)
    # print ct.json_countType,ct.json_countVol
    # df = get_sina_all_json_dd(ct.json_countType, ct.json_countVol)
    # df = get_sina_all_json_dd('0', '1')
    # print df.couts.sum()

    # print df
    # urltemp ='http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=100&sort=changepercent&asc=0&node=sh_a&symbol='

    # _parsing_Market_price_json(urltemp)
    # import ipdb;ipdb.set_trace()

    # df = get_sina_all_json_dd(1,0,num=10000)
    # print(len(df))


    print("getconfigBigCount:",getconfigBigCount(count=None, write=False))
    log.setLevel(LoggerFactory.INFO)
    df = get_market_price_sina_dd_realTime(dp='', vol='1', type='0')
    import ipdb;ipdb.set_trace()

    # df = get_sina_Market_json(market='all', showtime=True, num='100', retry_count=3, pause=0.001)
    df = get_sina_Market_json()
    print(df)
    print(df.loc['920274'])
    import ipdb;ipdb.set_trace()

    print(f'300502 ratio:{df.loc["300502"].ratio}')
    for mk in ['sh','sz','cyb']:
        df=get_sina_Market_json(mk,num=100)
        # print df.loc['600581']
        print("mk:\t",len(df))
    import tushare as ts
    s_t=time.time()
    # df = ts.get_today_all()
    # print "len:%s,time:%0.2f"%(len(df),time.time()-s_t)
    # print df[:1]
    # _get_sina_json_dd_url()
    print("Big_Count:",sina_json_Big_Count())

    # print getconfigBigCount(write=True)
    # sys.exit(0)
    # post_login()
    # get_wencai_Market_url(filter='热门股')
    # df = get_sina_Market_json('all')
    # print df[df.code == '600581']
    # print(df[:1],df.shape)
    # sys.exit()
    top_now = get_market_price_sina_dd_realTime(df, '2', type)
    print(top_now[:1])
    # sys.exit(0)
    # dd = get_sina_all_json_dd('0', '4')
    dd = get_sina_all_json_dd('2')
    print("")
    print(dd[:2])
    df = get_sina_dd_count_price_realTime(dd)
    # df = get_sina_all_json_dd('0', '1')
    print(len(df))
    print(df[:2])
    # df=get_market_price_sina_dd_realTime(df,'0','1')
    # df=get_sina_dd_count_price_realTime()
    # df=df.drop_duplicates('code')
    # df=df.set_index('code')
    # _write_to_csv(df,'readdata3')
    # print ""
    # print format_for_print(df[:10])
    # print df[df.index=='601919']
    # print len(df)
    # print "\033[1;37;4%dm%s\033[0m" % (1 > 0 and 1 or 2, get_sina_tick_jscct.code('002399'))
    # print get_sina_tick_js_LastPrice('002399')
    # print "ra:",sl.get_work_time_ratio()
    # dd = get_sina_tick_js_LastPrice(['002399','002399','601919','601198'])
    # print(type(dd))


    sys.exit(0)
    # up= df[df['trade']>df['settlement']]
    # print up[:2]
    # df=get_sina_all_json_dd(type='3')
    # print df[:10]
    # df=get_sina_Market_url()
    # for x in df:print ":",x
    df = pd.DataFrame()
    # dz=get_sina_Market_json('sz_a')
    # ds=get_sina_Market_json('sh_a')
    dc = get_sina_Market_json('all')
    # df=df.concat(dz,ignore_index=True)
    # df=df.append(ds,ignore_index=True)
    df = pd.concat([df,dc], ignore_index=True)
    # df=df[df['changepercent']<5]
    # df = df[df['changepercent'] > 0.2]

    # dd=df[(df['open'] <= df['low']) ]
    # dd=df[(df['open'] <= df['low']) ]
    print(df[:2], len(df.index))
    # da[da['changepercent']<9.9].
    # dd=df[(df['open'] <= df['low']) ]
    # dd=df[(df['open'] <= df['low']) ]
    # dd[dd['trade'] >= dd['high']*0.99]
    # sys.exit(0)
