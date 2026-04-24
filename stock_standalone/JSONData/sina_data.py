# -*- encoding: utf-8 -*-
from __future__ import annotations
import json
import os
import re
import sys
import time
import threading

sys.path.append("..")
# import pandas as pd
# import numpy as np
import requests

# from JSONData import tdx_hdf5_api as h5a
# from JSONData import realdatajson as rl
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct
h5a = cct.LazyModule('JSONData.tdx_hdf5_api')
rl = cct.LazyModule('JSONData.realdatajson')
pd = cct.LazyModule('pandas')
np = cct.LazyModule('numpy')
from JohnsonUtil import commonTips as cct
from JohnsonUtil.commonTips import timed_ctx,print_timing_summary
from JohnsonUtil import LoggerFactory
log = LoggerFactory.getLogger("sina_data")
# import trollius as asyncio
# from trollius.coroutines import From
import datetime
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
import aiohttp
import asyncio

def file_modified_days_ago(path: str) -> int:
    """
    返回文件最后修改时间距离现在的天数
    """
    mtime = os.path.getmtime(path)  # 秒级时间戳
    modified_time = datetime.datetime.fromtimestamp(mtime)
    now = datetime.datetime.now()
    return (now - modified_time).days

def get_base_path() -> str:
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

def get_stock_code_path() -> Optional[str]:
    """
    获取并验证 stock_codes.conf

    逻辑：
      1. 优先使用 BASE_DIR/stock_codes.conf
      2. 不存在 → 从 JSONData/stock_codes.conf 释放
      3. 校验文件
    """
    default_path = os.path.join(BASE_DIR, "stock_codes.conf")

    # --- 1. 直接存在 ---
    if os.path.exists(default_path):
        if os.path.getsize(default_path) >= 0:
            log.info(f"使用本地配置: {default_path}")
            return default_path
        else:
            log.warning("配置文件存在但为空，将尝试重新释放")

    # --- 2. 释放默认资源 ---
    cfg_file = cct.get_resource_file(
        rel_path="JSONData/stock_codes.conf",
        out_name="stock_codes.conf",
        BASE_DIR=BASE_DIR
    )

    # --- 3. 校验释放结果 ---
    if not cfg_file:
        log.error("获取 stock_codes.conf 失败（释放阶段）")
        return None

    if not os.path.exists(cfg_file):
        log.error(f"释放后文件仍不存在: {cfg_file}")
        return None

    if os.path.getsize(cfg_file) == 0:
        log.error(f"配置文件为空: {cfg_file}")
        return None

    log.info(f"使用内置释放配置: {cfg_file}")
    return cfg_file

class StockCode:
    start_t: float
    STOCK_CODE_PATH: Optional[str] = "stock_codes.conf"
    encoding: str
    stock_code_path: str
    exceptCount: Optional[int]
    stock_codes: Optional[List[str]]

    def __init__(self) -> None:
        self.start_t = time.time()
        # self.STOCK_CODE_PATH = os.path.join(BASE_DIR,"stock_codes.conf")
        self.STOCK_CODE_PATH = get_stock_code_path()
        if not self.STOCK_CODE_PATH:
            log.error("stock_codes.conf 加载失败，程序无法继续运行")

        self.encoding = 'gbk'
        self.stock_code_path = self.get_stock_code_path_func()
        self.exceptCount = cct.GlobalValues().getkey('exceptCount')
        log.info(f'stock_code_path: {os.path.getsize(self.stock_code_path)}')
        # file_days = file_modified_days_ago(self.stock_code_path)
        if  self.exceptCount is None and (not os.path.exists(self.stock_code_path) or os.path.getsize(self.stock_code_path) < 500):
            stock_codes = self.get_stock_codes(True)
            log.info(("create:%s counts:%s" % (self.stock_code_path, len(stock_codes))))
        if self.exceptCount is None and cct.creation_date_duration(self.stock_code_path) > 5:
            stock_codes = self.get_stock_codes(True)
        log.info(("date_duration days:%s %s read stock_codes.conf" % (cct.creation_date_duration(self.stock_code_path), len(self.get_stock_codes()))))

        self.stock_codes = None

    # @property
    def get_stock_code_path_func(self) -> str:
        return os.path.join(os.path.dirname(__file__), self.STOCK_CODE_PATH)

    def update_stock_codes(self) -> List[str]:
        """获取所有股票 ID 到 all_stock_code 目录下"""
        # 122.10.4.234 www.shdjt.com
        # https://site.ip138.com/www.shdjt.com/
        '''
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
        
        stock_codes = grep_stock_codes.findall(response.text)
        stock_codes = list(set([elem for elem in stock_codes if elem.startswith(('60', '30', '00','688','43','83','87','92'))]))
        '''

        df = rl.get_sina_Market_json('all')
        stock_codes = df.index.tolist()
        if len(stock_codes) < 5300:
            log.error(f"update_stock_codes codes:{len(stock_codes)} < 5300 get_sina_Market_json获取数据不全,停止更新")
            return (self.get_stock_codes())
        # stock_info_bj_name_code_df = stock_info_bj_name_code()
        # bj_list = stock_info_bj_name_code_df['证券代码'].tolist()
        # stock_codes.extend(bj_list)
        log.error("update_stock_codes codes:%s" % (len(stock_codes)))
        with open(self.stock_code_path, 'w') as f:
            f.write(json.dumps(dict(stock=stock_codes)))
        return stock_codes
    # @property

    def get_stock_codes(self, realtime: bool = False) -> List[str]:
        """[summary]

        [获取所有股票 ID 到 all_stock_code 目录下]

        Keyword Arguments:
            realtime {bool} -- [description] (default: {False})

        Returns:
            [type] -- [description]
        """
        # print "days:",cct.creation_date_duration(self.stock_code_path)
        is_trading_time = cct.get_trade_date_status() and (930 <= cct.get_now_time_int() <= 1500)
        if realtime and is_trading_time:
            # all_stock_codes_url = 'http://www.shdjt.com/js/lib/astock.js'
            # grep_stock_codes = re.compile('~(\d+)`')
            # response = requests.get(all_stock_codes_url)
            # stock_codes = grep_stock_codes.findall(response.text)
            # stock_codes = [elem for elem in stock_codes if elem.startswith(('6','30','00'))]
            # df= rl.get_sina_Market_json('all')
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
# ⚡ [INTERNAL-GLOBAL] 进程级共享资源助手 (用于跨模块加载同步)
import builtins
def _get_shared_res(name, default_factory):
    if not hasattr(builtins, name):
        setattr(builtins, name, default_factory())
    return getattr(builtins, name)

class Sina:
    """新浪免费行情获取"""
    # ⚡ [CORE-CACHE] 进程内跨模块路径唯一的共享资源，严格封装于 Sina 内部
    _MEM_CACHE = _get_shared_res('_HG_SINA_HDF5_MEM_CACHE', dict)
    _LOAD_LOCK = _get_shared_res('_HG_SINA_HDF5_LOAD_LOCK', threading.RLock)
    _LOADING_ST = _get_shared_res('_HG_SINA_HDF5_LOADING', dict)

    grep_stock_detail: re.Pattern
    sina_stock_api: str
    stock_data: List[str]
    stock_codes: List[str]
    stock_with_exchange_list: List[str]
    max_num: int
    start_t: float
    dataframe: pd.DataFrame
    hdf_name: str
    table: str
    sina_limit_time: Optional[Union[int, str]]
    cname: bool
    encoding: str
    sinaheader: Dict[str, str]
    agg_cache: Any
    stockcode: Optional[StockCode]
    stock_code_path: Optional[str]
    stock_list: List[str]
    request_num: int

    def __init__(self, readonly: bool = False) -> None:
        self.readonly = readonly
        import pandas as pd
        import numpy as np
        # self.grep_stock_detail = re.compile(r'(\d+)=([^\S][^,]+?)%s' %
        # (r',([\.\d]+)' * 29,))   #\n特例A (4)
        self.grep_stock_detail = re.compile(
            r'(\d+)=([^\n][^,]+.)%s%s' % (r',([\.\d]+)' * 29, r',(\d{4}-\d{2}-\d{2}),(\d{2}:\d{2}:\d{2})'))
        # 新增指数解析正则 (带字母前缀)
        self.grep_index_detail = re.compile(
            r'([a-z]{2}\d+)=([^\n][^,]+.)%s%s' % (r',([\.\d]+)' * 29, r',(\d{4}-\d{2}-\d{2}),(\d{2}:\d{2}:\d{2})'))
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
        self.hdf_name = 'sina_data'
        self.table = 'all'
        self.sina_limit_time = cct.sina_limit_time
        pd.options.mode.chained_assignment = None
        self.market_type = None
        self.cname = False
        self.encoding = 'gbk'
        self.sinaheader = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0',
            'referer': 'http://finance.sina.com.cn',
            'Connection': 'keep-alive',
            }
        self.agg_cache = cct.GlobalValues() # 用于聚合缓存
        self.stockcode = None
        self.stock_code_path = None
        self.stock_list = []
        self.request_num = 0
        # self.agg_cache 已经在 init 中通过 GlobalValues() 实例化

    def get_int_time(self, timet: float) -> int:
        return int(time.strftime("%H:%M:%S", time.localtime(timet))[:6].replace(':', ''))

    def load_stock_codes(self, all_codes: Optional[List[str]] = None) -> None:
        if all_codes is not None:
            self.stock_codes = list(set(all_codes))
        else:
            # 确保 self.stock_code_path 已被赋值
            if self.stock_code_path and os.path.exists(self.stock_code_path):
                with open(self.stock_code_path) as f:
                    self.stock_codes = list(set(json.load(f)['stock']))
            else:
                log.error("stock_code_path is not set or file does not exist in load_stock_codes")
        
        # 统一内存级别剔除停牌股
        excluded_codes = cct.GlobalValues().getkey('suspended_codes') or []
        if excluded_codes:
            original_len = len(self.stock_codes)
            self.stock_codes = [c for c in self.stock_codes if c not in excluded_codes]
            if len(self.stock_codes) < original_len:
                log.info(f"Session过滤停牌/无效股: {original_len - len(self.stock_codes)} 只")

        # if self.market_type == 'all' and len(self.stock_codes) > 5000:
        #     code_index = self.set_stock_codes_index_init(['999999','399001','399006'], index=True,append_stock_codes=True)
        #     log.debug(f'code_index  in self.stock_codes: { "sz399001" in self.stock_codes} count:{len(self.stock_codes)}')

    def _filter_suspended(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        统一检测并剔除停牌/无效股票，并更新内存缓存
        """
        if df is None or df.empty:
            return df
            
        # 判定条件优化：只有 open, now, buy, sell 全为 0 才视为停牌。
        # 如果 buy/sell > 0，说明只是暂时没成交，不应永久屏蔽。
        query_str = 'open == 0 and now == 0 and buy == 0 and sell == 0'
        if 'close' in df.columns:
            query_str = 'open == 0 and close == 0 and now == 0 and buy == 0 and sell == 0'
            
        suspended = df.query(query_str)
        if len(suspended) > 0:
            new_suspended = suspended.index.tolist()
            now_int = cct.get_now_time_int()
            
            # 🚦 策略优化：
            # 09:45 之前被判定为“无数据”的票，仅在本轮刷新中剔除（防止 UI 显示全 0），
            # 但不加入 `suspended_codes` 全局黑名单，给“晚开盘/冷门票”留出观察时间。
            # 09:45 之后仍无任何报价成交的票，才视为确实停牌，永久加入黑名单以节省后续 IO。
            if now_int > 945:
                log.info(f"检测到停牌股: {len(new_suspended)} 只, 加入 Session 禁刷列表")
                excluded = cct.GlobalValues().getkey('suspended_codes') or []
                excluded.extend(new_suspended)
                cct.GlobalValues().setkey('suspended_codes', list(set(excluded)))
            else:
                # 集合竞价期间(09:15-09:25)通常不剔除，除非完全没数据
                # 这里我们选择在 09:45 前只做临时剔除
                log.info(f"活跃保护期（09:45前）: 暂时过滤 {len(new_suspended)} 只无成交/无报价股票，不加入黑名单")
            
            df = df.drop(new_suspended)
            
        return df

    def format_age(self,seconds: float) -> str:
        if seconds is None:
            return "N/A"

        seconds = int(max(0, seconds))

        days = seconds // 86400
        seconds %= 86400

        hours = seconds // 3600
        seconds %= 3600

        minutes = seconds // 60
        seconds %= 60

        if days > 0:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    @property
    def all(self) -> pd.DataFrame:
        """获取所有实时数据 (优化 HDF5 加载逻辑)"""
        self.stockcode = StockCode()
        self.stock_code_path = self.stockcode.stock_code_path
        self.market_type = "all"
        all_codes = self.stockcode.get_stock_codes()
        self.load_stock_codes(all_codes)
        time_s = time.time()
        cache_key = f"Sina_all_snapshot_{self.hdf_name}_{self.table}"
        sina_limit_time_int: int = int(self.sina_limit_time) if self.sina_limit_time is not None else 60

        # [LOCKING] 确保同一时间只有一个线程在执行 Sina.all 的刷新逻辑（Thundering Herd protection）
        with self._LOAD_LOCK:
            # 重新检查一次缓存，防止在等待锁的过程中其他线程已经更新了缓存
            cached_item = self._MEM_CACHE.get(cache_key)
            if cached_item:
                c_df = cached_item.get('df')
                c_time = cached_item.get('time', 0)
                if c_df is not None and not c_df.empty:
                    if not cct.get_work_time() or (time.time() - c_time < sina_limit_time_int):
                        return c_df

            # 1. 尝试从 HDF5 加载历史数据 (通过统一缓存入口)
            sina_limit_time_int: int = int(self.sina_limit_time) if self.sina_limit_time is not None else 60
            # [FIX] 严重性能问题：Sina.all 是抓取快照的，绝对不能使用 _load_hdf_hist_unified 去载入 172MB 的 MultiIndex 轨迹！
            # 否则会导致 DataPublisher 每次都收到几百万行去遍历，瞬间撑爆内存。
            h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=None, limit_time=sina_limit_time_int)
            
            # 核心修正：如果请求包含关键指数（999999），但载入的缓存中缺失该代码，则强制执行实时抓取以同步 HDF5
            if h5 is not None and len(h5) > 0:
                if '999999' not in h5.index.tolist():
                    log.info("Sina.all: Cache missing index 999999, forcing live refresh to sync HDF5.")
                    h5 = None

            if h5 is not None and len(h5) > 0:
                # 基础预处理与质量校验 (Streamlined)
                if 'ticktime' in h5.columns:
                    # 只获取第一个非零 ticktime 用于判断数据鲜度 (Age)
                    valid_ticktimes = h5['ticktime'].dropna()

                    if not valid_ticktimes.empty:
                        now_dt = pd.Timestamp.now()
                        try:
                            # 🔥 取最大值（最新tick）
                            ticktime_val = valid_ticktimes.max()
                            if isinstance(ticktime_val, pd.Timestamp):
                                last_dt = ticktime_val
                            elif isinstance(ticktime_val, (int, float)) and ticktime_val > 1e9:
                                last_dt = pd.to_datetime(ticktime_val, unit='s')
                            elif isinstance(ticktime_val, str) and ('-' in ticktime_val or '/' in ticktime_val):
                                last_dt = pd.to_datetime(ticktime_val)
                            else:
                                dt_val = h5.loc[valid_ticktimes.idxmax(), 'dt'] if 'dt' in h5.columns else None
                                t = pd.to_datetime(str(ticktime_val)).time()
                                if dt_val and isinstance(dt_val, str) and '-' in dt_val:
                                    last_dt = pd.to_datetime(f"{dt_val} {t}")
                                else:
                                    last_dt = now_dt.replace(hour=t.hour, minute=t.minute, second=t.second)
                                    if last_dt > now_dt:
                                        last_dt -= pd.Timedelta(days=1)
                            l_time = (now_dt - last_dt).total_seconds()
                        except Exception as e:
                            log.warning(f"Ticktime parse failed: {e}")
                            l_time = 99999

                        now_int = cct.get_now_time_int()
                        is_trade_day = cct.get_trade_date_status()
                        work_time_now = cct.get_work_time()
                        
                        pre_open_force_hdf = 845 <= now_int < 915
                        auction_time = 915 <= now_int < 925
                        pre_open_lock = 925 <= now_int < 930
                        
                        is_today_data = (last_dt.date() == now_dt.date())
                        if is_today_data and work_time_now and 'dt' in h5.columns:
                            today_str = now_dt.strftime('%Y-%m-%d')
                            today_ratio = (h5['dt'] == today_str).mean()
                            if today_ratio < 0.96:
                                 log.info(f"Sina.all: Cache freshness uneven (Today ratio: {today_ratio:.2%}), forcing full refresh.")
                                 is_today_data = False

                        normal_return_hdf = (not work_time_now) or (is_trade_day and l_time < sina_limit_time_int and is_today_data)
                        return_hdf_status = pre_open_force_hdf or pre_open_lock or normal_return_hdf
                        
                        if ((auction_time and l_time < sina_limit_time_int) or (not auction_time and return_hdf_status)):
                            log.info("Return HDF5 data early (recent:%s)" % self.format_age(l_time))
                            if self.agg_cache.getkey('agg_metrics') is None or self.agg_cache.getkey('agg_metrics').empty:
                                self.agg_cache.setkey('agg_metrics', h5.copy())
                            return self._sanitize_indicators(self.combine_lastbuy(h5))

                log.info(f"HDF5 exists but not recent enough or quality poor, continuing to fetch...")
            else:
                log.info("HDF5 data missing or empty in unified cache")

            # 2. 从网络获取最新数据
            self.stock_with_exchange_list = [cct.code_to_symbol(code) for code in self.stock_codes]
            all_index_symbols = ['sh000001', 'sz399001', 'sz399006', 'sz399005', 'sh000688' ,'bj899050','sz159915','sh588930']
            for index_symbol in all_index_symbols:
                if index_symbol not in self.stock_with_exchange_list:
                    self.stock_with_exchange_list.append(index_symbol)
            
            self.stock_list = []
            self.request_num = len(self.stock_with_exchange_list) // self.max_num
            for range_start in range(self.request_num):
                num_start = self.max_num * range_start
                num_end = self.max_num * (range_start + 1)
                request_list = ','.join(self.stock_with_exchange_list[num_start:num_end])
                self.stock_list.append(request_list)
            
            if len(self.stock_with_exchange_list) > (self.request_num * self.max_num):
                num_end = self.request_num * self.max_num
                request_list = ','.join(self.stock_with_exchange_list[num_end:])
                self.stock_list.append(request_list)
                self.request_num += 1
            
            df = self.get_stock_data()

            # 3. 整合网络数据与聚合指标 (agg_metrics)
            if df is not None and not df.empty:
                agg_data = self.agg_cache.getkey('agg_metrics')
                cache_needs_rebuild = (agg_data is None or agg_data.empty)
                
                if not cache_needs_rebuild:
                    for c_check in ['nlow', 'nhigh']:
                        if c_check in agg_data.columns:
                            if (agg_data[c_check] <= 0).sum() / len(agg_data) > 0.3:
                                cache_needs_rebuild = True; break
                
                h5_hist = self._load_hdf_hist_unified(debug=False)
                if cache_needs_rebuild:
                    log.info("Rebuilding aggregator cache metrics from MultiIndex HDF5...")
                    df_final = self._rebuild_agg_cache(h5_hist, df)
                else:
                    self._update_agg_cache(df, h5_hist)
                    df_final = cct.combine_dataFrame(agg_data, df)

                df_final = self.combine_lastbuy(df_final)
                for c in ['nhigh', 'nlow', 'nclose']:
                    if c not in df_final.columns:
                        source_col = c[1:] if c.startswith('n') else 'close'
                        df_final[c] = df_final[source_col] if source_col in df_final.columns else df_final.get('close', 0)
                
                if not self.readonly:
                    h5a.write_hdf_db(self.hdf_name, df_final.copy(), self.table, index=False)
                
                for c in ['nclose', 'nstd']:
                    if c in df_final.columns: df_final[c] = df_final[c].round(2)
                if 'ticktime' in df_final.columns:
                    df_final.loc[:, 'ticktime'] = df_final['ticktime'].astype(str).apply(lambda x: x if ':' in x else f"{x.zfill(6)[:2]}:{x.zfill(6)[2:4]}:{x.zfill(6)[4:6]}")

                log.info("Sina.all consolidated finalized.")
                df = df_final
            else:
                df = self._filter_suspended(df) if df is not None else pd.DataFrame()
            
            if df is None or df.empty:
                return pd.DataFrame()

            df_final = self._sanitize_indicators(df)

            # 6. 定期保存 MultiIndex 轨迹数据
            now_time = time.time()
            last_mi_save_val: float = 0.0
            last_mi_save_obj = self.agg_cache.getkey('last_mi_save_time')
            if last_mi_save_obj is not None:
                try:
                    last_mi_save_val = float(last_mi_save_obj)
                except (ValueError, TypeError):
                    last_mi_save_val = 0.0
            
            if now_time - last_mi_save_val > 300 or getattr(self, 'mock_simulator_mode', False):
                h5_mi_fname = 'sina_MultiIndex_data'
                limit_time_int: int = int(self.sina_limit_time) if self.sina_limit_time is not None else 60
                h5_mi_table = 'all_' + str(limit_time_int)
                if cct.get_work_time() and not self.readonly:
                    mi_cols = ['code', 'ticktime', 'close', 'high', 'low', 'llastp', 'volume', 'lastbuy']
                    mi_df = df_final.copy()
                    if not isinstance(mi_df.index, pd.RangeIndex):
                        mi_df = mi_df.reset_index()
                    if 'code' in mi_df.columns and 'ticktime' in mi_df.columns:
                        valid_cols = [c for c in mi_cols if c in mi_df.columns]
                        mi_df = mi_df[valid_cols]
                        if not pd.api.types.is_datetime64_any_dtype(mi_df['ticktime']):
                             mi_df['ticktime'] = pd.to_datetime(mi_df['ticktime'], errors='coerce')
                        mi_df['code'] = mi_df['code'].astype(str)
                        mi_df = mi_df.set_index(['code', 'ticktime'])
                        h5a.write_hdf_db(h5_mi_fname, mi_df, table=h5_mi_table, index=True, MultiIndex=True)
                        self.agg_cache.setkey('last_mi_save_time', now_time)
                        log.info("Saved MultiIndex history (sync) to %s (len: %d)" % (h5_mi_fname, len(mi_df)))

            # 7. [INTERNAL-SYNC] 同步至 Sina 类属性共享缓存
            if not self.readonly:
                self._MEM_CACHE[cache_key] = {'df': df_final.copy(), 'time': time.time()}
            return df_final

    def _update_agg_cache(self, df_latest: pd.DataFrame,h5_hist: pd.DataFrame) -> None:
        """增量更新内存中的聚合指标 (带时间窗口控制)"""
        if df_latest is None or len(df_latest) == 0:
            return
            
        agg_metrics: Optional[pd.DataFrame] = self.agg_cache.getkey('agg_metrics')
        
        # 1. 提取当前批次的统计值
        stats: pd.DataFrame
        if 'code' in df_latest.columns:
            stats = df_latest.groupby('code').agg({'open': 'first', 'low': 'min', 'high': 'max', 'close': 'last'})
        else:
            stats = df_latest.groupby(level=0).agg({'open': 'first', 'low': 'min', 'high': 'max', 'close': 'last'})
            
        # 强制索引为字符串
        stats.index = stats.index.astype(str)
        
        # 容错：如果 low/high 为 0，使用 close 兜底
        stats.loc[stats['low'] <= 0, 'low'] = stats['close']
        stats.loc[stats['high'] <= 0, 'high'] = stats['close']

        if agg_metrics is None:
            new_agg = stats.rename(columns={'low': 'nlow', 'high': 'nhigh', 'close': 'nclose'})
            new_agg.index = new_agg.index.astype(str)
            new_agg['nstd'] = np.nan
            # 初次创建时强制包含 open 守卫
            new_agg['nlow'] = new_agg[['nlow', 'open']].min(axis=1)
            new_agg['nhigh'] = new_agg[['nhigh', 'open']].max(axis=1)
            self.agg_cache.setkey('agg_metrics', new_agg)
            log.info("Initialized AggregatorCache with %d codes (OpenGuard included)" % len(new_agg))
            return
            
        if not agg_metrics.index.dtype == object:
             agg_metrics.index = agg_metrics.index.astype(str)
            
        now_int = cct.get_now_time_int()
        
        common_codes = agg_metrics.index.intersection(stats.index)
        if len(common_codes) > 0:
            # nlow: 强制修正 0.0 或 NaN，并开启 Open 守卫
            agg_metrics.loc[common_codes, 'nlow'] = agg_metrics.loc[common_codes, 'nlow'].fillna(0)
            idx_low_fix = (agg_metrics.loc[common_codes, 'nlow'] <= 0)
            if idx_low_fix.any():
                fix_codes = common_codes[idx_low_fix]
                agg_metrics.loc[fix_codes, 'nlow'] = stats.loc[fix_codes, 'low']
            
            # [OPEN-GUARD] 无论何时，最低价必须包含开盘价
            agg_metrics.loc[common_codes, 'nlow'] = agg_metrics.loc[common_codes, 'nlow'].combine(stats.loc[common_codes, 'open'], min)
                
            if now_int <= 945:
                 agg_metrics.loc[common_codes, 'nlow'] = agg_metrics.loc[common_codes, 'nlow'].combine(stats.loc[common_codes, 'low'], min)

            # nhigh: 强制修正 0.0 或 NaN，并开启 Open 守卫
            agg_metrics.loc[common_codes, 'nhigh'] = agg_metrics.loc[common_codes, 'nhigh'].fillna(0)
            idx_high_fix = (agg_metrics.loc[common_codes, 'nhigh'] <= 0)
            if idx_high_fix.any():
                fix_codes_h = common_codes[idx_high_fix]
                agg_metrics.loc[fix_codes_h, 'nhigh'] = stats.loc[fix_codes_h, 'high']

            # [OPEN-GUARD] 无论何时，最高价必须包含开盘价
            agg_metrics.loc[common_codes, 'nhigh'] = agg_metrics.loc[common_codes, 'nhigh'].combine(stats.loc[common_codes, 'open'], max)

            if now_int <= 1030:
                 agg_metrics.loc[common_codes, 'nhigh'] = agg_metrics.loc[common_codes, 'nhigh'].combine(stats.loc[common_codes, 'high'], max)
        
        time_h5_hist = time.time()
        all_func = {'low': 'nlow', 'high': 'nhigh', 'close': 'nclose'}
        startime = '9:25:00'
        # endtime = '10:00:00'
        endtime = '10:30:00'

        run_col = ['close', 'low', 'high']
        df_latest = self.get_col_agg_df(h5_hist, df_latest, run_col, all_func, startime, endtime)
        
        # ⚡ [CRITICAL FIX] 同步计算结果回缓存
        # 确保已存在的 common_codes 也能更新到从轨迹中算出的早盘指标
        for col in ['nlow', 'nhigh', 'nclose']:
            if col in df_latest.columns:
                agg_metrics.loc[common_codes, col] = df_latest.loc[common_codes, col].fillna(agg_metrics.loc[common_codes, col])

        log.info(f'update_agg_cache df_latest sync done, duration:{time.time()-time_h5_hist:.1f}')

        new_codes = stats.index.difference(agg_metrics.index)
        if len(new_codes) > 0:
            new_df = df_latest.loc[new_codes, [c for c in ['nlow', 'nhigh', 'nclose'] if c in df_latest.columns]]
            # 补齐：如果轨迹中也没有，用 stats 兜底
            for col in ['nlow', 'nhigh', 'nclose']:
                source = col[1:] if col.startswith('n') else col
                new_df[col] = new_df[col].fillna(stats.loc[new_codes, source])
            
            agg_metrics = pd.concat([agg_metrics, new_df])
            
        if not self.readonly:
            self.agg_cache.setkey('agg_metrics', agg_metrics)

    def _rebuild_agg_cache(self, h5_hist: Optional[pd.DataFrame], df_current: pd.DataFrame) -> pd.DataFrame:
        """从历史 MultiIndex 数据中重建聚合缓存 (优化兼容日期前缀)"""
        # time_s = time.time()
        # agg_df: pd.DataFrame
        # if h5_hist is not None and not h5_hist.empty:
        #     if not isinstance(h5_hist.index, pd.MultiIndex):
        #          h5_hist = h5_hist.set_index(['code', 'ticktime'], append=False)
            
        #     # 提取时间部分 HH:MM:SS，兼容 '2025-12-18 09:25:00' 格式
        #     tick_times = h5_hist.index.get_level_values('ticktime').astype(str)
        #     time_only = tick_times.str.split().str[-1]
            
        #     agg_low = h5_hist[time_only <= '09:45:00'].groupby(level=0)['low'].min().to_frame('nlow')
        #     agg_high = h5_hist[time_only <= '10:30:00'].groupby(level=0)['high'].max().to_frame('nhigh')
        #     agg_close = h5_hist.groupby(level=0)['close'].last().to_frame('nclose')
            
        #     h5_std = h5_hist[(time_only >= '09:25:00') & (time_only <= '09:35:00')]
        #     agg_std: pd.DataFrame
        #     if not h5_std.empty:
        #         agg_std = h5_std.groupby(level=0)['close'].std().to_frame('nstd').round(2)
        #     else:
        #         agg_std = pd.DataFrame(columns=['nstd'])
        #     agg_df = pd.concat([agg_low, agg_high, agg_close, agg_std], axis=1)
        # else:
        #     agg_df = pd.DataFrame(columns=['nlow', 'nhigh', 'nclose', 'nstd'])
        """从历史 MultiIndex 数据中重建聚合缓存，nclose/nlow/nhigh/nstd 使用 get_col_agg_df 计算"""
        time_s = time.time()
        agg_df: pd.DataFrame
        if h5_hist is not None and not h5_hist.empty:
            if not isinstance(h5_hist.index, pd.MultiIndex):
                h5_hist = h5_hist.set_index(['code', 'ticktime'], append=False)
            time_h5_hist = time.time()
            run_col = ['low', 'high']
            all_func = {'low': 'nlow', 'high': 'nhigh', 'close': 'nclose'}
            startime = '9:25:00'
            # endtime = '10:00:00'
            endtime = '10:30:00'
            # 使用 get_col_agg_df 计算 nclose/nlow/nhigh/nstd
            # with timed_ctx("_calc_intraday_vwapNhigh", warn_ms=80):
            agg_df = self.get_col_agg_df(h5_hist, df_current, run_col, all_func, startime, endtime)

            endtime = '10:30:00'
            run_col = ['close']

            # agg_df = self.get_col_agg_df(h5_hist, agg_df, run_col, all_func, startime, endtime)
            with timed_ctx("_calc_intraday_vwapNclose", warn_ms=80):
                agg_df = self.get_col_agg_df(h5_hist, agg_df, run_col, all_func, startime, endtime)
            # cct.print_timing_summary()
            # agg_df['nclose'] = self._calc_intraday_vwap(h5_hist, agg_df, startime, endtime)

            log.info(f'get_col_agg_df_duration_time:{time.time()-time_h5_hist:.1f}')
        else:
            agg_df = pd.DataFrame(columns=['nlow', 'nhigh', 'nclose', 'nstd'])

        curr_stats: pd.DataFrame
        if 'code' in df_current.columns:
            curr_stats = df_current.groupby('code').agg({'open': 'first', 'low': 'min', 'high': 'max', 'close': 'last'})
        else:
            curr_stats = df_current.groupby(level=0).agg({'open': 'first', 'low': 'min', 'high': 'max', 'close': 'last'})
            
        # 统一索引类型为字符串
        agg_df.index = agg_df.index.astype(str)
        curr_stats.index = curr_stats.index.astype(str)
        
        all_codes = agg_df.index.union(curr_stats.index)
        rebuild_df = pd.DataFrame(index=all_codes)
        rebuild_df.index = rebuild_df.index.astype(str)
        now_int = cct.get_now_time_int()

        # nlow: 优先使用历史记录，修正 0.0 或 NaN
        if 'nlow' in agg_df.columns:
            src = agg_df['nlow']
        elif 'low' in agg_df.columns:
            src = agg_df['low']
        elif 'close' in agg_df.columns:
            src = agg_df['close']
        else:
            src = 0

        rebuild_df['nlow'] = (
            src.reindex(rebuild_df.index)
               .fillna(0)
            if hasattr(src, 'reindex')
            else 0
        )
        # rebuild_df['nlow'] = agg_df['nlow'].reindex(rebuild_df.index).fillna(0)

        idx_low_fix = (rebuild_df['nlow'] <= 0)
        if idx_low_fix.any():
            codes_fix = rebuild_df.index[idx_low_fix]
            rebuild_df.loc[codes_fix, 'nlow'] = curr_stats['low'].reindex(codes_fix).fillna(0)
            # 二次兜底
            idx_still_zero = (rebuild_df.loc[codes_fix, 'nlow'] <= 0)
            if idx_still_zero.any():
                 codes_still = codes_fix[idx_still_zero]
                 rebuild_df.loc[codes_still, 'nlow'] = curr_stats['close'].reindex(codes_still)
        
        # [OPEN-GUARD] 无论何时，最低价必须考虑到开盘价
        rebuild_df['nlow'] = rebuild_df['nlow'].combine(curr_stats['open'].reindex(rebuild_df.index), min)

        if now_int <= 945:
            rebuild_df['nlow'] = rebuild_df['nlow'].combine(curr_stats['low'].reindex(rebuild_df.index), min)
        if 'nhigh' not in agg_df.columns:
            agg_df['nhigh'] = agg_df['close']
        if 'nclose' not in agg_df.columns:
            agg_df['nclose'] = agg_df['close']
        # nhigh: 优先使用历史记录，修正 0.0 或 NaN
        rebuild_df['nhigh'] = agg_df['nhigh'].reindex(rebuild_df.index).fillna(0)
        idx_high_fix = (rebuild_df['nhigh'] <= 0)
        if idx_high_fix.any():
            codes_fix_h = rebuild_df.index[idx_high_fix]
            rebuild_df.loc[codes_fix_h, 'nhigh'] = curr_stats['high'].reindex(codes_fix_h).fillna(0)
            # 二次兜底
            idx_still_zero_h = (rebuild_df.loc[codes_fix_h, 'nhigh'] <= 0)
            if idx_still_zero_h.any():
                 codes_still_h = codes_fix_h[idx_still_zero_h]
                 rebuild_df.loc[codes_still_h, 'nhigh'] = curr_stats['close'].reindex(codes_still_h)
        
        # [OPEN-GUARD] 无论何时，最高价必须考虑到开盘价
        rebuild_df['nhigh'] = rebuild_df['nhigh'].combine(curr_stats['open'].reindex(rebuild_df.index), max)

        if now_int <= 1030:
            rebuild_df['nhigh'] = rebuild_df['nhigh'].combine(curr_stats['high'].reindex(rebuild_df.index), max)
        else:
            # [LOGIC-FIX] 即使过了 10:30，如果发现轨迹计算出的 nhigh 异常偏低（甚至低于开盘价），
            # 也应根据实时 API 抓到的 high 字段进行一次合理性对齐（前提是轨迹极度残缺）
            mask_bad_high = (rebuild_df['nhigh'] < rebuild_df['nlow']) | (rebuild_df['nhigh'] == 0)
            if mask_bad_high.any():
                rebuild_df.loc[mask_bad_high, 'nhigh'] = curr_stats['high'].reindex(rebuild_df.index)[mask_bad_high]
            
        # # nclose: 直接用当前价更新
        # rebuild_df['nclose'] = curr_stats['close'].reindex(rebuild_df.index).fillna(agg_df['nclose'].reindex(rebuild_df.index))
        # # 三次兜底：确保 nclose 不为 0
        # rebuild_df.loc[rebuild_df['nclose'] <= 0, 'nclose'] = curr_stats['close'].reindex(rebuild_df.index)


        # nclose：优先使用历史聚合值，仅在缺失 / 非法时才用 Web 回补或当前 close 兜底
        rebuild_df['nclose'] = agg_df['nclose'].reindex(rebuild_df.index)

        mask_nclose_fix = rebuild_df['nclose'].fillna(0) <= 0
        if mask_nclose_fix.any():
            fix_codes = rebuild_df.index[mask_nclose_fix].tolist()
            log.info(f"Targeting {len(fix_codes)} codes for nclose web-backfill...")
            for i, code in enumerate(fix_codes):
                if i > 50: break # 防止重启延迟过高
                web_vwap = self._fetch_sina_intraday_kline(code)
                if web_vwap is not None:
                    rebuild_df.loc[code, 'nclose'] = web_vwap
            
            # 最后的彻底兜底
            mask_final = rebuild_df['nclose'].fillna(0) <= 0
            if mask_final.any():
                rebuild_df.loc[mask_final, 'nclose'] = \
                    curr_stats['close'].reindex(rebuild_df.index)[mask_final]


        if 'nstd' in agg_df.columns:
             rebuild_df['nstd'] = agg_df['nstd'].reindex(rebuild_df.index)
        else:
             rebuild_df['nstd'] = np.nan

        self.agg_cache.setkey('agg_metrics', rebuild_df)
        log.info("Rebuild agg cache. size:%s time:%.2f" % (len(rebuild_df), time.time() - time_s))
        return cct.combine_dataFrame(df_current, rebuild_df)

    def _fetch_sina_intraday_kline(self, code: str, target_time: str = '10:30:00') -> Optional[float]:
        """从新浪 API 获取当日 5 分钟 K 线并计算截止到 target_time 的 VWAP。"""
        try:
            symbol = ('sh%s' % code) if code.startswith(('60', '688', '11')) else ('sz%s' % code)
            if code.startswith(('43', '83', '87', '92')): symbol = 'bj%s' % code
            
            url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=5&ma=no&datalen=100"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code != 200: return None
            data = response.json()
            if not data or not isinstance(data, list): return None
            
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
            total_amount = 0.0
            total_volume = 0.0
            for bar in data:
                dt_str = bar.get('day', '')
                if not dt_str.startswith(today_str): continue
                if dt_str.split(' ')[-1] > target_time: continue
                c = float(bar.get('close', 0))
                v = float(bar.get('volume', 0))
                total_amount += c * v
                total_volume += v
                
            return total_amount / total_volume if total_volume > 0 else None
        except Exception as e:
            log.warning(f"Failed to fetch intraday kline for {code}: {e}")
            return None


    def get_cname_code(self, cname: str) -> Union[str, int]:
        self.cname  = True
        dm = self.all
        df = dm[dm.name == cname]
        if len(df) == 1:
            code = df.index[0]
        else:
            code = 0
        return code

    def get_code_cname(self, code: str) -> str:
        self.cname  = True
        dm = self.all
        df = dm[dm.index == code]
        if len(df) == 1:
            name = df.name[0]
        else:
            name = code
        return name
        
    def market(self, market: str) -> pd.DataFrame:
        if market in ['all']:
            return self.all
        else:

            self.market_type = market
            self.table = 'all' # ⚡ [FIX] 统一从 all 表读取，减小 IO 复杂度，避免子市场表缺失导致误报日志
            self.stockcode = StockCode()
            self.stock_code_path = self.stockcode.stock_code_path
            all_codes = self.stockcode.get_stock_codes()
            self.load_stock_codes(all_codes)
            if market == 'sh':
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('60') or elem.startswith('688')]
                self.stock_with_exchange_list = [('sh%s') % stock_code for stock_code in self.stock_codes]
            elif market == 'sz':
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('00')]
                self.stock_with_exchange_list = [('sz%s') % stock_code for stock_code in self.stock_codes]
            elif market == 'cyb':
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('30')]
                self.stock_with_exchange_list = [('sz%s') % stock_code for stock_code in self.stock_codes]
            elif market == 'kcb':
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('688')]
                self.stock_with_exchange_list = [('sh%s') % stock_code for stock_code in self.stock_codes]
            elif market == 'bj':
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith(('43', '83', '87', '92'))]
                self.stock_with_exchange_list = [('bj%s') % stock_code for stock_code in self.stock_codes]
            
            self.stock_codes = list(set(self.stock_codes))
            time_s = time.time()
            
            # 确保 sina_limit_time 是 int
            sina_limit_time_int: int = int(self.sina_limit_time) if self.sina_limit_time is not None else 60
            
            # 0. [INTERNAL CACHE CHECK] - 优先检查 Sina 类属性共享缓存
            cache_key = f"Sina_market_snapshot_{market}_{self.hdf_name}_{self.table}"
            cached_item = self._MEM_CACHE.get(cache_key)
            if cached_item:
                c_df = cached_item.get('df')
                c_time = cached_item.get('time', 0)
                if c_df is not None and not c_df.empty:
                    if not cct.get_work_time() or (time.time() - c_time < sina_limit_time_int):
                        log.info(f"Sina.market({market}): Returning class-level shared cache (Age: {time.time()-c_time:.1f}s)")
                        return c_df

            h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=self.stock_codes, limit_time=sina_limit_time_int)
            log.info("h5a market: %s stocksTime:%0.2f" % (market, time.time() - time_s))

            if h5 is not None and not h5.empty:
                # 获取第一个非零 ticktime 逻辑保持不变
                valid_ts = h5[h5.ticktime != 0].ticktime
                if not valid_ts.empty:
                    ts = valid_ts.iloc[0]
                    ts_str: str
                    if isinstance(ts, (pd.Timestamp, datetime.datetime)):
                        ts_str = ts.strftime('%H%M%S')
                    elif isinstance(ts, str):
                        ts_str = ts.replace(":", "")[-6:]
                    else:
                        ts_str = str(ts)[-6:]
                    
                    ticktime = int(ts_str)
                    
                    # o_time 校验 (增强版：同时校验日期是否匹配今日)
                    o_time_df = h5[h5.timel != 0].timel
                    if not o_time_df.empty:
                        o_time_val = o_time_df.iloc[0]
                        o_time_int = self.get_int_time(o_time_val)
                        
                        # 🚦 增加日期一致性判定：如果是交易日且是早盘，缓存日期不对则绝对不返回
                        now_dt = pd.Timestamp.now()
                        today_str = now_dt.strftime('%Y-%m-%d')
                        is_trade_day = cct.get_trade_date_status()
                        work_time_now = cct.get_work_time()
                        valid_date = True
                        if is_trade_day and work_time_now:
                            if 'dt' in h5.columns:
                                # 对于单一市场，可以要求更高的今日占比 (99%+)
                                today_ratio = (h5['dt'] == today_str).mean()
                                if today_ratio < 0.99:
                                    valid_date = False
                                    log.info(f"Sina.market({market}): Stale date detected in cache (Ratio: {today_ratio:.2%}), ignoring HDF.")
                        
                        if valid_date and ((o_time_int >= 1500 and ticktime >= 1500) or (o_time_int < 1500 and ticktime < 1500)):
                            h5 = self.combine_lastbuy(h5)
                            return self._filter_suspended(h5)

            self.stock_list = []
            self.request_num = len(self.stock_with_exchange_list) // self.max_num
            for range_start in range(self.request_num):
                num_start = self.max_num * range_start
                num_end = self.max_num * (range_start + 1)
                request_list = ','.join(self.stock_with_exchange_list[num_start:num_end])
                self.stock_list.append(request_list)
            
            if self.request_num > 0 and len(self.stock_with_exchange_list) > (self.request_num * self.max_num):
                num_end_final = self.request_num * self.max_num
                request_list_final = ','.join(self.stock_with_exchange_list[num_end_final:])
                self.stock_list.append(request_list_final)
                self.request_num += 1
            elif self.request_num == 0:
                request_list_final = ','.join(self.stock_with_exchange_list)
                self.stock_list.append(request_list_final)
                self.request_num = 1
            
            df_res = self._filter_suspended(self.get_stock_data())
            # [INTERNAL-SYNC] 同步至 Sina 类属性共享缓存 (只读模式不更新全局缓存)
            if not self.readonly:
                self._MEM_CACHE[cache_key] = {'df': df_res.copy(), 'time': time.time()}
            return df_res


    # https://github.com/jinrongxiaoe/easyquotation
    async def get_stocks_by_range(self, index: int, session: aiohttp.ClientSession) -> None:
        url = self.sina_stock_api + self.stock_list[index]
        async with session.get(url=url, headers=self.sinaheader) as response:
            response.encoding = self.encoding
            result = await response.text()
            self.stock_data.append(result)

    async def _fetch_all_stocks(self, session: aiohttp.ClientSession):
        tasks = [self.get_stocks_by_range(i, session) for i in range(self.request_num)]
        if not tasks:
            tasks = [self.get_stocks_by_range(0, session)]
        await asyncio.gather(*tasks)

    def fill_other_data(self, df):
        time_s = time.time()
        if df is None or len(df) == 0:
            log.warning("Failed to fetch fresh data from Sina")
            return pd.DataFrame()

        # 3. 确定是否需要从历史轨迹重建 (Anytime Recovery)
        agg_data = self.agg_cache.getkey('agg_metrics')
        cache_needs_rebuild = False
        if agg_data is None or agg_data.empty:
            cache_needs_rebuild = True
        elif self.market_type != 'all' and agg_data is not None and not agg_data.empty:
            cache_needs_rebuild = False
        else:
            # 质量校验：如果 0.0 比例过高，强制重建
            for c_check in ['nlow', 'nhigh']:
                if c_check in agg_data.columns:
                    zero_ratio = (agg_data[c_check] <= 0).sum() / len(agg_data)
                    if zero_ratio > 0.3:
                        log.warning("In-memory agg_metrics poor (zero_ratio %s: %.2f), rebuilding" % (c_check, zero_ratio))
                        cache_needs_rebuild = True
                        break
        # 4. 如果缓存缺失，优先从 MultiIndex 历史恢复，然后再应用当前 Tick
        now_int = cct.get_now_time_int()
        if cache_needs_rebuild or (self.market_type == 'all' and 925 < now_int <= 1030):
            log.info("AggregatorCache poor or missing, rebuilding from MultiIndex HDF5...")
            l_limit_time = int(cct.sina_limit_time)
            h5_mi_fname = 'sina_MultiIndex_data'
            h5_mi_table = 'all_' + str(l_limit_time)
            # h5_hist = h5a.load_hdf_db(h5_mi_fname, h5_mi_table, timelimit=False, MultiIndex=True)
            h5_hist = h5a.load_hdf_db(h5_mi_fname, h5_mi_table, timelimit=False)
            df_final = self._rebuild_agg_cache(h5_hist, df)
            # 此时内存缓存已由 _rebuild_agg_cache 设置好
        else:
            if self.market_type != 'all':
                # ⚡ [CORE-FIX] 交换参数顺序：让新数据 df 覆盖旧缓存 agg_data
                df_final = cct.combine_dataFrame(agg_data, df)
                if 'nhigh' not in df_final.columns:
                    df_final['nhigh'] = df_final['close']
                if 'nclose' not in df_final.columns:
                    df_final['nclose'] = df_final['close']
            else:
                # 正常更新逻辑：先更新增量，再合并 (仅限 all 流程)
                h5_mi_fname = 'sina_MultiIndex_data'
                l_limit_time = int(cct.sina_limit_time)
                h5_mi_table = 'all_' + str(l_limit_time)
                # h5_hist = h5a.load_hdf_db(h5_mi_fname, h5_mi_table, timelimit=False, MultiIndex=True)
                h5_hist = h5a.load_hdf_db(h5_mi_fname, h5_mi_table, timelimit=False)
                self._update_agg_cache(df, h5_hist)
                agg_data = self.agg_cache.getkey('agg_metrics')
                # ⚡ [CORE-FIX] 交换参数顺序：让新数据 df 覆盖旧缓存 agg_data
                df_final = cct.combine_dataFrame(agg_data, df)
                if 'nhigh' not in df_final.columns:
                    df_final['nhigh'] = df_final['close']
                if 'nclose' not in df_final.columns:
                    df_final['nclose'] = df_final['close']
        # 5. 合并 lastbuy 并持久化
        df_final = self.combine_lastbuy(df_final)
        
        # ⚡ [FIX] 彻底解决内存缓存泄露问题：如果不是 'all' 模式，强行过滤掉不属于当前市场的代码
        # 防止由于 agg_metrics cache (GlobalValues) 共享导致的 SH 代码出现在 SZ 结果中
        if self.market_type is not None and self.market_type != 'all' and self.stock_codes:
            df_final = df_final[df_final.index.isin(self.stock_codes)]
            
        # 使用 index=False 避免反转索引，且先 copy 避免影响返回的对象
        if self.market_type is not None and self.market_type == 'all' and not self.readonly:
            h5a.write_hdf_db(self.hdf_name, df_final.copy(), self.table, index=False)

        if df_final is not None and len(df_final) > 0:
            # 格式化数值
            for col in ['nclose', 'nstd']:
                if col in df_final.columns:
                    df_final[col] = df_final[col].round(2)
            
            if 'ticktime' in df_final.columns:
                if df_final is not None and not df_final.empty:
                    df_final.loc[:, 'ticktime'] = df_final['ticktime'].astype(str).apply(lambda x: x if ':' in x else f"{x.zfill(6)[:2]}:{x.zfill(6)[2:4]}:{x.zfill(6)[4:6]}")

        log.info("Sina.all (optimized) total time:%0.2f" % (time.time() - time_s))
        if df_final is None or df_final.empty:
             return pd.DataFrame()
             
        df_final = self._sanitize_indicators(df_final)
             
        # 6. 定期保存 MultiIndex 轨迹数据 (用于程序重启后重建 nlow/nhigh)
        # 每 5 分钟保存一次，避免 I/O 过载
        now_time = time.time()
        # 显式转换以消除 Pylance 类型警告
        last_mi_save_val: float = 0.0
        last_mi_save_obj = self.agg_cache.getkey('last_mi_save_time')
        if last_mi_save_obj is not None:
            try:
                last_mi_save_val = float(last_mi_save_obj)
            except (ValueError, TypeError):
                last_mi_save_val = 0.0
        
        if now_time - last_mi_save_val > 300:
            h5_mi_fname = 'sina_MultiIndex_data'
            # 显式转换为 int 以消除类型警告
            limit_time_int: int = int(self.sina_limit_time) if self.sina_limit_time is not None else 60
            h5_mi_table = 'all_' + str(limit_time_int)
            # 仅在交易时间内记录
            if cct.get_work_time() and cct.get_now_time_int() > cct.sina_MultiIndex_startTime:
                # 构造 MultiIndex 精简格式轨迹: [code, ticktime, close, high, low, llastp, volume, lastbuy]
                # 这必须与 format_response_data 中的 mi_cols 保持绝对一致以避免 ValueError
                mi_cols = ['code', 'ticktime', 'close', 'high', 'low', 'llastp', 'volume', 'lastbuy']
                # mi_cols = ['code', 'ticktime', 'open', 'close', 'high', 'low', 'llastp', 'volume', 'lastbuy']
                mi_df = df_final.loc[:, [c for c in mi_cols if c in df_final.columns]].copy()

                # mi_df = self.clean_ohlcv_zero(mi_df)

                if isinstance(mi_df, pd.DataFrame):
                    # 1. 无条件 Reset Index，确保所有数据 flattened，防止 ticktime 藏在 Index 中漏过类型检查
                    if not isinstance(mi_df.index, pd.RangeIndex):
                         mi_df = mi_df.reset_index()

                    # 2. 确保 'code' 和 'ticktime' 存在，并在 columns 中
                    if 'code' in mi_df.columns and 'ticktime' in mi_df.columns:
                        # 3. 强制转换 ticktime 为 datetime64，严格匹配 format_response_data 的写入类型
                        if not pd.api.types.is_datetime64_any_dtype(mi_df['ticktime']):
                             mi_df['ticktime'] = pd.to_datetime(mi_df['ticktime'], errors='coerce')
                        
                        # 4. 设置 MultiIndex
                        mi_df = mi_df.set_index(['code', 'ticktime'])

                    # 使用 index=True 强制保存索引，确保 MultiIndex 能被正确持久化
                    if self.market_type is not None and self.market_type == 'all' and not self.readonly:
                        h5a.write_hdf_db(h5_mi_fname, mi_df, table=h5_mi_table, index=True, MultiIndex=True)
                        self.agg_cache.setkey('last_mi_save_time', now_time)
                        log.info("Saved MultiIndex history (sync) to %s cols:%s" % (h5_mi_fname, mi_df.columns.tolist()))

        return df_final

    def get_stock_data(self, retry_count: int = 3, pause: float = 0.01) -> pd.DataFrame:
        for _ in range(retry_count):
            time.sleep(pause)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            async def run():
                async with aiohttp.ClientSession() as session:
                    await self._fetch_all_stocks(session)
            
            loop.run_until_complete(run())
            log.debug('get_stock_data_loop')
            
            df = self.format_response_data()
            if df is not None:
                df = self.fill_other_data(df)
                return self._filter_suspended(df)
            else:
                return pd.DataFrame()

        raise IOError(ct.NETWORK_URL_ERROR_MSG)

    def ensure_code_ticktime_index(self,df: pd.DataFrame, name='df'):
        """
        强制保证 df.index.names == ['code','ticktime']
        """
        if isinstance(df.index, pd.MultiIndex):
            names = list(df.index.names)
            if names == ['code', 'ticktime']:
                return df
            if set(names) >= {'code', 'ticktime'}:
                return df.reorder_levels(['code','ticktime']).sort_index()
        
        # 走到这里：不是 MultiIndex，或 names=[None]
        if 'code' in df.columns and 'ticktime' in df.columns:
            return df.set_index(['code','ticktime'], drop=True).sort_index()

        raise RuntimeError(
            f"[{name}] index 结构非法: "
            f"index.names={df.index.names}, "
            f"columns={list(df.columns)}"
        )


    def drop_tick_all_zero(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        删除无效 tick：
        - close == 0
        - volume == 0
        保留索引结构（适用于 MultiIndex）
        """
        if df.empty:
            return df

        needed = {'close', 'volume'}
        if not needed.issubset(df.columns):
            return df

        mask_valid = (df['close'] != 0) & (df['volume'] != 0)

        return df.loc[mask_valid]



    def drop_tick_all_zero_all_zero(self,df: pd.DataFrame) -> pd.DataFrame:
        """
        删除 tick 中 OHLC + volume 全为 0 的脏行
        - 不 reset index
        - 保留 MultiIndex
        - 适用于 tick / 分时
        """
        if df.empty:
            return df

        cols = [c for c in ('close', 'high', 'low', 'volume') if c in df.columns]
        if not cols:
            return df

        mask_valid = df[cols].ne(0).any(axis=1)
        return df.loc[mask_valid]

    def clean_ohlcv_zero(self, df: pd.DataFrame, ohlcv_cols=None, check_existing=True) -> pd.DataFrame:
        """
        清理 OHLCV 全为 0 的行，严格保留原 index 结构。
        RangeIndex 会保留，MultiIndex 也会保留。
        """
        if df.empty:
            return df

        # 1️⃣ 自动识别 OHLCV 列
        if ohlcv_cols is None:
            ohlcv_cols = [c for c in ('low', 'close', 'volume') if c in df.columns]
        if not ohlcv_cols:
            return df

        # 2️⃣ 高性能检查是否需要清理
        if check_existing:
            has_all_zero = df[ohlcv_cols].eq(0).all(axis=1).any()
            if not has_all_zero:
                return df

        # 3️⃣ 行过滤
        mask_valid = df[ohlcv_cols].ne(0).any(axis=1)
        # 4️⃣ 保留原 index 类型

        if isinstance(df.index, pd.RangeIndex):
            # 用 iloc 保留 RangeIndex
            valid_pos = np.flatnonzero(mask_valid.values)
            return df.iloc[valid_pos].reset_index(drop=True)
        else:
            # MultiIndex 或其他 index
            return df.loc[mask_valid].reset_index(drop=True)


    def format_response_data(self, index: bool = False) -> Optional[pd.DataFrame]:
        stocks_detail = ''.join(self.stock_data)
        # print stocks_detail
        result = self.grep_stock_detail.finditer(stocks_detail)
        # stock_dict = dict()
        list_s = []
        # 1. 解析个股 (旧逻辑)
        for stock_match_object in result:
            # ⚡ [FIX] 针对 300058 等创业板股票的精准抢救
            # 原逻辑 isalpha() 会把 sz300058 也跳过，因为 sz 是字母，导致其只能去 index 循环碰运气
            # 改进：仅当 prefix 为 'sh' 且 code 为 '000xxx' (指数段) 时才跳过，普通的 sz/sh 6xxx 应该进 Stock 循环
            start_pos = stock_match_object.start()
            code_matched = stock_match_object.group(1)
            prefix = stocks_detail[max(0, start_pos-2):start_pos].lower()
            
            # 如果是 sh 且 code 以 000 开头，大概率是指数（如 sh000001），跳过进入 index 循环
            if prefix == 'sh' and code_matched.startswith('000'):
                continue
            # 这里的 alpha 检查还是保留一层兜底但要排除 sz/sh 正常前缀
            if start_pos >= 2 and prefix.isalpha() and prefix not in ['sz', 'sh', 'bj']:
                continue
            stock = stock_match_object.groups()
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
                 'turnover': float(stock[10]),
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
                 
        # 2. 新增指数解析轨道 (不干扰数字匹配)
        idx_result = self.grep_index_detail.finditer(stocks_detail)
        for idx_match_object in idx_result:
            idx_stock = idx_match_object.groups()
            symbol = idx_stock[0]
            # 统一映射映射
            if symbol == 'sh000001':
                code = '999999'
            elif symbol == 'sh000688':
                code = '999688'
            else:
                code = symbol[2:]
                
            list_s.append(
                {'code': code,
                 'name': idx_stock[1],
                 'open': float(idx_stock[2]),
                 'close': float(idx_stock[3]),
                 'now': float(idx_stock[4]),
                 'high': float(idx_stock[5]),
                 'low': float(idx_stock[6]),
                 'buy': float(idx_stock[7]),
                 'sell': float(idx_stock[8]),
                 'volume': int(idx_stock[9]),
                 'turnover': float(idx_stock[10]),
                 'b1_v': int(idx_stock[11]),
                 'b1': float(idx_stock[12]),
                 'b2_v': int(idx_stock[13]),
                 'b2': float(idx_stock[14]),
                 'b3_v': int(idx_stock[15]),
                 'b3': float(idx_stock[16]),
                 'b4_v': int(idx_stock[17]),
                 'b4': float(idx_stock[18]),
                 'b5_v': int(idx_stock[19]),
                 'b5': float(idx_stock[20]),
                 'a1_v': int(idx_stock[21]),
                 'a1': float(idx_stock[22]),
                 'a2_v': int(idx_stock[23]),
                 'a2': float(idx_stock[24]),
                 'a3_v': int(idx_stock[25]),
                 'a3': float(idx_stock[26]),
                 'a4_v': int(idx_stock[27]),
                 'a4': float(idx_stock[28]),
                 'a5_v': int(idx_stock[29]),
                 'a5': float(idx_stock[30]),
                 'dt': (idx_stock[31]),
                 'ticktime': (idx_stock[32])})
#        print list_s
        # df = pd.DataFrame.from_dict(stock_dict,columns=ct.SINA_Total_Columns)
        if len(list_s) == 0:
            log.error("Sina Url error:%s" % (self.sina_stock_api + ','.join(self.stock_codes[:2])))
            return pd.DataFrame() # Robust check for empty results

        df = pd.DataFrame(list_s, columns=ct.SINA_Total_Columns)

        # 2. 确保 ticktime 是完整的 YYYY-MM-DD HH:MM:SS 格式
        if df.empty:
             return df
        df['dt'] = df['dt'].astype(str).str[:10]
        tt_raw = df['ticktime'].astype(str)
        # 如果长度为 8 (HH:MM:SS)，则补齐日期前缀
        mask_short = tt_raw.str.len() == 8
        if mask_short.any():
            df.loc[mask_short, 'ticktime'] = df.loc[mask_short, 'dt'] + ' ' + tt_raw.loc[mask_short]
        
        # 3. 统一转换为 Timestamp 对象 (避免混合类型)
        df['ticktime'] = pd.to_datetime(df['ticktime'], errors='coerce')
        
        # 检测未来 Tick 并纠偏至上一个交易日 (API 有时在非交易时段返回 dt 为今日但数据是旧的)
        now = pd.Timestamp.now()
        future_mask = df['ticktime'] > (now + pd.Timedelta(minutes=3))
        if future_mask.any():
            last_date = cct.get_last_trade_date()
            log.warning(f"[TICK-纠偏] 检测到未来时间(SINA-DETAIL), 纠偏至 {last_date}: {df.loc[future_mask, 'ticktime'].iloc[0]}")
            # 重新按上个交易日解析
            df.loc[future_mask, 'ticktime'] = pd.to_datetime(
                last_date + ' ' + df.loc[future_mask, 'ticktime'].dt.strftime('%H:%M:%S'), 
                errors='coerce'
            )
        
        if df.empty:
             return df
             
        dt_v = df.dt.value_counts().index[0]
        # 宽容过滤：主日期外，额外保留映射后的指数代码段
        # 保护指数和核心基准不被日期过滤掉 (Sina 有时指数日期更新滞后)
        index_codes = ['999999', '399001', '399006', '399678', '399005', '999688', '000300', '000905', '000852', '899050']
        df = df[(df.dt >= dt_v) | (df['code'].isin(index_codes))]

        df.rename(columns={'close': 'llastp'}, inplace=True)
        df['b1_vv'] = df['b1_v'].map(lambda x: int(x / 100 / 10000))
        now_time_int = cct.get_now_time_int()
        if (915 < now_time_int < 926):
            df['close'] = df['buy']
            df['open'] = df['buy']
            # 仅在现值为 0 或 NaN 时才使用 buy 竞价，保护已有极值
            idx_low = (df['low'] <= 0) | (df['low'].isna())
            df.loc[idx_low, 'low'] = df.loc[idx_low, 'buy']
            idx_high = (df['high'] <= 0) | (df['high'].isna())
            df.loc[idx_high, 'high'] = df.loc[idx_high, 'buy']
            df['volume'] = ((df['b1_v'] + df['b2_v'])).map(lambda x: x)

        elif (0 < now_time_int <= 915):
            df['buy'] = df['now']
            df['close'] = df['now']
            df['open'] = df['now']
            # 只在字段缺失时才强制覆盖，防止非交易时段抹消历史极值
            idx_low_pre = (df['low'] <= 0) | (df['low'].isna())
            df.loc[idx_low_pre, 'low'] = df.loc[idx_low_pre, 'now']
            idx_high_pre = (df['high'] <= 0) | (df['high'].isna())
            df.loc[idx_high_pre, 'high'] = df.loc[idx_high_pre, 'now']

        else:
            df['close'] = df['now']
            
        # 全局保底：如果 open/high/low 为 0 且 now 有效，则使用 now 补齐，防止聚合指标出现 0.0
        for col in ['open', 'high', 'low']:
            idx_zero = (df[col] <= 0) & (df['now'] > 0)
            if idx_zero.any():
                df.loc[idx_zero, col] = df.loc[idx_zero, 'now']

        df['nvol'] = df['volume']
        df = df.drop_duplicates('code')
        df = df.fillna(0)
        df = df.set_index('code')
        if index:
            # 强化映射防护：仅对特定指数代码段执行反向映射，且防止 999999 被二次反转
            df.index = list(map((lambda x: str(1000000 - int(x))
                            if (x.startswith('00000') and x != '999999') else x), df.index))
        # 确认指数在列 (用于 Debug)
        if '999999' in df.index:
            log.info("Sina.format_response_data: Index 999999 successfully generated and indexed.")
        log.info("hdf:all %s %s" % (len(df), len(self.stock_codes)))
        
        # --- 分别处理轨迹数据(mi)和实时数据(dd) ---
        # 1. 轨迹历史数据 (仅精简 8 列) -> sina_MultiIndex_data.h5
        logtime = cct.get_config_value_ramfile('sina_logtime')
        otime =  cct.get_config_value_ramfile('sina_logtime',int_time=True)
        is_workt_time = cct.get_work_time()
        
        if now_time_int > 925 and (not index and ( cct.get_work_time(otime) or is_workt_time )):
            time_s = time.time()
            df.index = df.index.astype(str)
            df.ticktime = df.ticktime.astype(str)

            # df.ticktime = list(map(lambda x, y: str(x) + ' ' + str(y), df.dt, df.ticktime))
            mask = df['ticktime'].astype(str).str.len() <= 8

            df.loc[mask, 'ticktime'] = df.loc[mask, 'dt'].astype(str) + ' ' + df.loc[mask, 'ticktime']

            df.ticktime = pd.to_datetime(df.ticktime, format='%Y-%m-%d %H:%M:%S', errors='coerce')

            # 检测未来 Tick 并纠偏至上一个交易日
            now = pd.Timestamp.now()
            future_mask = df['ticktime'] > (now + pd.Timedelta(minutes=3))
            if future_mask.any():
                last_date = cct.get_last_trade_date()
                log.warning(f"[TICK-纠偏] 检测到未来时间(SINA-LIST), 纠偏至 {last_date}: {df.loc[future_mask, 'ticktime'].iloc[0]}")
                # 重新按上个交易日解析
                df.loc[future_mask, 'ticktime'] = pd.to_datetime(
                    last_date + ' ' + df.loc[future_mask, 'ticktime'].dt.strftime('%H:%M:%S'), 
                    errors='coerce'
                )

            # # 1. 统一为字符串
            # df['dt'] = df['dt'].astype(str).str[:10]
            # tt = df['ticktime'].astype(str)

            # # 2. 判断是否已经是完整 datetime
            # is_full_dt = tt.str.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')

            # # 3. 只对“不是完整 datetime”的行进行补齐
            # tt.loc[~is_full_dt] = (
            #     df.loc[~is_full_dt, 'dt'] + ' ' +
            #     tt.loc[~is_full_dt].str[-8:]
            # )

            # # 4. 转换为 datetime（兜底不炸）
            # df['ticktime'] = pd.to_datetime(
            #     tt,
            #     format='%Y-%m-%d %H:%M:%S',
            #     errors='coerce'
            # )


            if logtime == 0:
                cct.get_config_value_ramfile('sina_logtime',currvalue=time.time(),xtype='time',update=True)
                df['lastbuy'] = (list(map(lambda x, y: y if int(x) == 0 else x,
                                          df['close'].values, df['llastp'].values)))
                cct.GlobalValues().setkey('lastbuydf', df['lastbuy']) 

            else:
                if (cct.GlobalValues().getkey('lastbuylogtime') is not None ) or self.lastbuy_timeout_status(logtime):
                    cct.get_config_value_ramfile('sina_logtime',currvalue=time.time(),xtype='time',update=True)
                    df['lastbuy'] = (list(map(lambda x, y: y if int(x) == 0 else x,
                                              df['close'].values, df['llastp'].values)))
                    cct.GlobalValues().setkey('lastbuylogtime', None) 
                    cct.GlobalValues().setkey('lastbuydf', df['lastbuy']) 
                else:
                    df = self.combine_lastbuy(df)
                            
            df_mi = df.copy()
            if 'code' not in df_mi.columns:
                df_mi = df_mi.reset_index()
            
            mi_cols = ['code', 'ticktime', 'close', 'high', 'low', 'llastp', 'volume', 'lastbuy']
            # mi_cols = ['code', 'ticktime', 'open', 'close', 'high', 'low', 'llastp', 'volume', 'lastbuy']

            if 'lastbuy' not in df_mi.columns:
                df_mi['lastbuy'] = df_mi['close'] if 'close' in df_mi.columns else 0
            
            df_mi_write = df_mi.loc[:, [c for c in mi_cols if c in df_mi.columns]]

            # if isinstance(df_mi_write.index, pd.RangeIndex):
            #     if 'code' in df_mi_write.columns and 'ticktime' in df_mi_write.columns:
            #         df_mi_write = df_mi_write.set_index(['code','ticktime'])

            # 调用清理函数
            # log.debug(f'index: {isinstance(df_mi_write.index, pd.RangeIndex)}')
            # df_mi_write = self.clean_ohlcv_zero(df_mi_write)

            # # 直接 reindex 取需要的列
            # # df_mi_write = df_mi.reindex(columns=[c for c in mi_cols if c in df_mi.columns])
            # df_mi_write = self.ensure_code_ticktime_index(df_mi_write)
            # df_mi_write = self.clean_ohlcv_zero(df_mi_write)

            if isinstance(df_mi_write.index, pd.RangeIndex):
                if 'code' in df_mi_write.columns and 'ticktime' in df_mi_write.columns:
                     df_mi_write = df_mi_write.set_index(['code', 'ticktime'])
            
            h5_mi_fname = 'sina_MultiIndex_data'
            limit_time_int = int(self.sina_limit_time) if self.sina_limit_time else 60
            h5_mi_table = 'all_' + str(limit_time_int)
            
            try:
                if is_workt_time and not self.readonly:
                    h5a.write_hdf_db(h5_mi_fname, df_mi_write, table=h5_mi_table, index=False, baseCount=500, append=False, MultiIndex=True, sizelimit=cct.sina_MultiIndex_limit)
                    log.info("Saved minimal mi_data: %s rows, cols: %s" % (len(df_mi_write), df_mi_write.columns.tolist()))
            except Exception as e:
                log.error(f"HDF5 Write Error for {h5_mi_table}: {e}")
                try:
                    # 尝试清理已损坏的文件，防止死循环
                    path = cct.get_ramdisk_path(h5_mi_fname)
                    if not path.endswith('.h5') and not os.path.exists(path):
                        path += '.h5'
                    
                    if os.path.exists(path):
                        os.remove(path)
                        log.warning(f"Deleted corrupt file: {path}")
                    
                    # 同时也清理 lock 文件
                    lock_path = path + '.lock'
                    if os.path.exists(lock_path):
                         os.remove(lock_path)
                except Exception as ex:
                    log.error(f"Failed to auto-delete corrupt file: {ex}")
            log.info("hdf5 class all (trajectory) time:%0.2f" % (time.time() - time_s))
            
        return df


    def lastbuy_timeout_status(self, logtime: Union[float, str]) -> bool:

        return (time.time() - float(logtime) > float(ct.sina_lastbuy_logtime))


    def combine_lastbuy(self, h5: pd.DataFrame) -> pd.DataFrame:
        if h5 is None or h5.empty:
            return h5
        agg_metrics = self.agg_cache.getkey('agg_metrics')
        # 1. lastbuy 兜底
        if 'lastbuy' not in h5.columns or (h5['lastbuy'].fillna(0) <= 0).any():
            lastbuydf = cct.GlobalValues().getkey('lastbuydf')
            if lastbuydf is not None:
                h5['lastbuy'] = lastbuydf.reindex(h5.index).fillna(0)
            elif agg_metrics is not None and 'nclose' in agg_metrics.columns:
                h5['lastbuy'] = agg_metrics.reindex(h5.index)['nclose'].fillna(0)

        # 2. nclose 只在缺失时修复（方案三）
        if agg_metrics is not None and 'nclose' in agg_metrics.columns:
            if 'nclose' not in h5.columns:
                h5['nclose'] = np.nan

            mask = h5['nclose'].fillna(0) <= 0
            if mask.any():
                h5.loc[mask, 'nclose'] = agg_metrics.reindex(h5.index)['nclose']
        
        return self._sanitize_indicators(h5)

    def _sanitize_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一清洗指标列中的 0.0 或 NaN 值，确保所有返回的数据都是健康的"""
        if df is None or df.empty:
            return df

        now_t = cct.get_now_time_int()  # 例如 931, 1459 这种整数时间

        is_trade_day = cct.get_trade_date_status()

        # 是否在交易时段内
        in_trade_time = (
               (925 <= now_t) 
        )
            # (925 <= now_t <= 1130) or
            # (1300 <= now_t <= 1500)
            
        # 交易日，但不在交易时间 → 直接返回
        if is_trade_day and not in_trade_time:
            return df

        # ⚡ [FIX] 针对停牌个股 (volume == 0) 的强制对齐逻辑
        # 防止由于 agg_metrics 或历史轨迹残留导致的 nclose 与现价偏离过大
        if 'volume' in df.columns and 'close' in df.columns:
            mask_suspended = (df['volume'] <= 0)
            if mask_suspended.any():
                for col in ['nlow', 'nhigh', 'nclose', 'lastbuy']:
                    if col in df.columns:
                        # 停牌个股：所有累计/对比指标均对齐至当前上报价格 (即最后收盘价)
                        df.loc[mask_suspended, col] = df.loc[mask_suspended, 'close']

        # 强制索引转为字符串 (兼容 MultiIndex)
        if isinstance(df.index, pd.MultiIndex):
            for i in range(df.index.nlevels):
                if not df.index.levels[i].dtype == object:
                     df.index = df.index.set_levels(df.index.levels[i].astype(str), level=i)
        else:
            if not df.index.dtype == object:
                df.index = df.index.astype(str)
        
        # print(f"{df.loc['600971'].nhigh}")
        # 目标列及其兜底列
        targets = [('nlow', 'low'), ('nhigh', 'high'), ('nclose', 'close'), ('lastbuy', 'close')]
        for target, fallback in targets:
            if target not in df.columns:
                continue
            # 只处理 NaN
            mask = df[target].isna()

            if mask.any() and fallback in df.columns:
                df.loc[mask, target] = df.loc[mask, fallback]

            # 再处理仍然 NaN 的
            mask_still = df[target].isna()
            if mask_still.any() and 'close' in df.columns:
                df.loc[mask_still, target] = df.loc[mask_still, 'close']

        # for target, fallback in targets:
        #     if target in df.columns:
        #         # 填充 NaN 为 0，方便统一判断
        #         df.loc[:, target] = df[target].fillna(0).values
        #         # 1. 基础修正 (针对 0.0)
        #         mask = (df[target] <= 0)
        #         if mask.any():
        #             if fallback in df.columns:
        #                  df.loc[mask, target] = df.loc[mask, fallback].fillna(0).values
                    
        #             mask_still = (df[target] <= 0)
        #             if mask_still.any() and 'close' in df.columns:
        #                  df.loc[mask_still, target] = df.loc[mask_still, 'close']

                # # 2. 一致性修正 (确保 nlow 不大于 low, nhigh 不小于 high)
                # if target == 'nlow' and 'low' in df.columns:
                #      # 如果 nlow 反而比今日最低价还高，说明指标由于某种原因落后或初始化错误，强制同步
                #      mask_invalid = (df['nlow'] > df['low']) & (df['low'] > 0)
                #      if mask_invalid.any():
                #           df.loc[mask_invalid, 'nlow'] = df.loc[mask_invalid, 'low']
                          
                # elif target == 'nhigh' and 'high' in df.columns:
                #      # 如果 nhigh 反而比今日最高价还低，强制同步
                #      mask_invalid_h = (df['nhigh'] < df['high']) & (df['high'] > 0)
                #      if mask_invalid_h.any():
                #           df.loc[mask_invalid_h, 'nhigh'] = df.loc[mask_invalid_h, 'high']

        # 处理 nstd
        if 'nstd' in df.columns:
            df.loc[df['nstd'].fillna(0) <= 0, 'nstd'] = np.nan
            
        return df

    def set_stock_codes_index_init(self, code: Union[str, List[str]], index: bool = False,append_stock_codes=False) -> List[str]:
        code_list: List[str]
        if not isinstance(code, list):
            code_list = code.split(',')
        else:
            code_list = code
        code_l: List[str] = []
        if index:
            for x in code_list:
                if x.startswith('999'):
                    code_l.append(str(1000000 - int(x)).zfill(6))
                else:
                    code_l.append(x)
            
            self.stock_codes = []
            for sc in code_l:
                # 如果已经带有 sh/sz/bj 前缀，则直接使用
                if sc.startswith(('sh', 'sz', 'bj')):
                    self.stock_codes.append(sc)
                # 000xxx 开头或通过 999 转换来的均为上证指数 (Sina)
                elif sc.startswith('0'):
                    self.stock_codes.append('sh%s' % sc)
                # 399xxx 开头为深证指数
                elif sc.startswith('399'):
                    self.stock_codes.append('sz%s' % sc)
                else:
                    # 默认根据 startswith('0') 逻辑兜底或默认 sz
                    prefix = 'sh' if sc.startswith('0') else 'sz'
                    self.stock_codes.append('%s%s' % (prefix, sc))
            # stock_codes_index = [('sh%s' if stock_code.startswith(('0')) else 'sz%s') % stock_code for stock_code in code_l]
            # if not append_stock_codes or len(self.stock_codes) == 0 :
            #     self.stock_codes  = stock_codes_index
            # else:
            #     self.stock_codes.extend(stock_codes_index)

        else:
            code_l = code_list
            self.stock_codes = [cct.code_to_symbol(stock_code) for stock_code in code_l]
        return code_l

    def get_stock_code_data(self, code: Union[str, List[str]], index: bool = False) -> pd.DataFrame:
        code_l = self.set_stock_codes_index_init(code, index)
        h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=code_l, index=index, limit_time=int(self.sina_limit_time))
        if h5 is not None:
            log.info("find index hdf5 data:%s" % (len(h5)))
            h5 = self.combine_lastbuy(h5)
            return h5
        if len(self.stock_codes) == 0:
            log.error("self.stock_codes is empty for code:%s" % code)
            return pd.DataFrame()
            
        self.url = self.sina_stock_api + ','.join(self.stock_codes)
        log.info("stock_list:%s" % self.url[:30])
        response = requests.get(self.url, headers=self.sinaheader)
        response.encoding = self.encoding
        self.stock_data.append(response.text)
        self.dataframe = self.format_response_data(index)
        if self.dataframe is None:
            return pd.DataFrame()
        cols = ['code', 'open', 'high', 'low', 'close']
        # code 通常是字符串或整数，先排除
        num_cols = ['open', 'high', 'low', 'close']
        # ds.loc[:, num_cols] = ds.loc[:, num_cols].round(2)
        self.dataframe.loc[:, num_cols] = (
            self.dataframe.loc[:, num_cols]
            .apply(pd.to_numeric, errors='coerce')
            .round(2)
        )
        return self.dataframe


    def get_stock_list_data(self, ulist: List[str], index: bool = False) -> pd.DataFrame:
        ulist = [stock_code  for stock_code in ulist if stock_code.startswith(('0','3','4','5', '6','8', '9'))]
        h5: Optional[pd.DataFrame] = None
        if index:
            ulist = self.set_stock_codes_index_init(ulist, index)
        else:
            h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=ulist, index=index)
            
        if h5 is not None and len(h5) >= len(ulist):
            log.info("hdf5 data:%s" % (len(h5)))
            h5 = self.combine_lastbuy(h5)
            return h5

        self.stock_data = []
        if len(ulist) > self.max_num:
            self.stock_list = []
            self.stock_with_exchange_list = [cct.code_to_symbol(stock_code) for stock_code in ulist]
            self.request_num = len(self.stock_with_exchange_list) // self.max_num
            for range_start in range(self.request_num):
                num_start = self.max_num * range_start
                num_end = self.max_num * (range_start + 1)
                request_list = ','.join(self.stock_with_exchange_list[num_start:num_end])
                self.stock_list.append(request_list)
            if len(self.stock_with_exchange_list) > (self.request_num * self.max_num):
                num_end_final = self.request_num * self.max_num
                request_list_final = ','.join(self.stock_with_exchange_list[num_end_final:])
                self.stock_list.append(request_list_final)
                self.request_num += 1

            log.debug('all:%s' % len(self.stock_list))
            return self.get_stock_data()
        else:
            if not index:
                self.stock_codes = [cct.code_to_symbol(stock_code) for stock_code in ulist]

            if len(self.stock_codes) == 0:
                log.error("self.stock_codes is empty for ulist:%s" % ulist)
            
            url_local = self.sina_stock_api + ','.join(self.stock_codes)
            log.info("stock_list:%s" % url_local[:30])
            response = requests.get(url_local, headers=self.sinaheader)
            response.encoding = self.encoding
            self.stock_data.append(response.text)
            self.dataframe = self.format_response_data(index)
        return self.dataframe

    def get_major_indices(self) -> pd.DataFrame:
        """获取主要大盘指数 (上证, 深证, 创业板, 科创50)"""
        # 使用映射后的全 6 位代码
        codes = ['999999', '399001', '399006', '999688']
        return self.get_stock_list_data(codes, index=True)



    def _calc_intraday_vwap_fast(self, h5: pd.DataFrame, startime=None, endtime=None) -> pd.DataFrame:
        if h5 is None or h5.empty:
            return pd.DataFrame()

        # 时间切片
        if startime or endtime:
            h5 = cct.get_limit_multiIndex_Row(h5,
                                              col=['close', 'volume'],
                                              start=startime,
                                              end=endtime)

        if h5 is None or len(h5) == 0:
            return pd.DataFrame()

        df = h5[['close', 'volume']].copy()

        if df.empty: return pd.DataFrame()

        # 2. 提取底层 NumPy 数组 (脱离 Pandas 索引对齐开销)
        # 获取每个 code 的分组边界索引（核心加速点：利用 MultiIndex 已排序的特性）
        codes = df.index.get_level_values(0).values
        # 找到每个 code 最后一行的位置
        diff_mask = np.concatenate([codes[1:] != codes[:-1], [True]])
        # 找到每个 code 第一行的位置
        first_mask = np.concatenate([[True], codes[1:] != codes[:-1]])

        close = df['close'].values
        volume = df['volume'].values

        # 3. 极限向量化计算成交量增量 (Vol Diff)
        # 用移位减法代替 groupby.diff()
        vol_diff = np.empty_like(volume)
        vol_diff[0] = volume[0]
        vol_diff[1:] = volume[1:] - volume[:-1]
        # 修正组间差异：每个 code 的第一行不应减去前一个 code 的最后一行
        vol_diff[first_mask] = volume[first_mask]
        
        # 过滤无效数据：将无效位置的增量设为 0
        invalid_mask = (close <= 0) | (vol_diff <= 0)
        vol_diff[invalid_mask] = 0
        amount_inc = close * vol_diff

        # 4. 关键：计算组内累计求和 (利用 np.cumsum 和 偏移)
        # 这种方法比 groupby.cumsum 快一个数量级
        cum_vol_all = np.cumsum(vol_diff)
        cum_amt_all = np.cumsum(amount_inc)

        # 减去上一个代码组的末尾累计值，实现组内 cumsum
        group_ends = np.where(diff_mask)[0]
        # 获取每个组之前的总偏移量
        v_offsets = np.zeros_like(cum_vol_all)
        a_offsets = np.zeros_like(cum_amt_all)
        
        # 获取前一组的累计值
        v_last_cum = cum_vol_all[group_ends[:-1]]
        a_last_cum = cum_amt_all[group_ends[:-1]]
        
        # 填充偏移量数组（通过重复填充）
        # 获取每组的长度
        group_lengths = np.diff(np.concatenate([[-1], group_ends]))
        v_offsets = np.repeat(np.concatenate([[0], v_last_cum]), group_lengths)
        a_offsets = np.repeat(np.concatenate([[0], a_last_cum]), group_lengths)

        # 计算 VWAP
        final_cum_vol = cum_vol_all - v_offsets
        final_cum_amt = cum_amt_all - a_offsets
        
        # 5. 只取每个 code 的最后一行结果
        # 避免除以 0
        with np.errstate(divide='ignore', invalid='ignore'):
            nclose_all = final_cum_amt / final_cum_vol
        
        # 提取结果
        res_v = nclose_all[diff_mask]
        res_k = df.index.get_level_values(0)[diff_mask]

        return pd.DataFrame({'nclose': res_v}, index=res_k)

    def _calc_intraday_vwap(self,
                            h5: pd.DataFrame,
                            startime: Optional[str] = None,
                            endtime: Optional[str] = None) -> pd.DataFrame:
        """
        计算分时VWAP（nclose）
        h5: MultiIndex (code, ticktime)
        返回: index=code, column=['nclose']
        """

        if h5 is None or len(h5) == 0:
            return pd.DataFrame()

        # 时间切片
        if startime or endtime:
            h5 = cct.get_limit_multiIndex_Row(h5,
                                              col=['close', 'volume'],
                                              start=startime,
                                              end=endtime)

        if h5 is None or len(h5) == 0:
            return pd.DataFrame()

        df = h5[['close', 'volume']].copy()

        # 去掉无效数据
        df = df[(df['close'] > 0) & (df['volume'] > 0)]

        if len(df) == 0:
            return pd.DataFrame()

        # 排序（非常重要）
        df = df.sort_index(level=1)

        # 转为普通列方便处理
        df = df.reset_index()

        # 计算增量成交量（你的volume是累计）
        df['vol_diff'] = df.groupby('code')['volume'].diff().fillna(df['volume'])

        # 增量成交额（近似，没有amount只能用close×vol）
        df['amount_inc'] = df['close'] * df['vol_diff']

        # 累计
        df['cum_amount'] = df.groupby('code')['amount_inc'].cumsum()
        df['cum_vol'] = df.groupby('code')['vol_diff'].cumsum()

        # VWAP
        df['nclose'] = df['cum_amount'] / df['cum_vol']

        # 只保留每个code最后一条
        result = df.groupby('code').last()[['nclose']]

        return result

    def get_col_agg_df(self, h5: pd.DataFrame, dd: pd.DataFrame, run_col: Union[List[str], Dict[str, str]], all_func: Dict[str, str], startime: Optional[str], endtime: Optional[str], freq: Optional[str] = '5T') -> pd.DataFrame:
        """
        聚合 MultiIndex DataFrame，按 code 聚合指标。
        """
        if h5 is None or len(h5) == 0:
            return dd
            
        time_n = time.time()
        if isinstance(run_col, str):
            run_col = [run_col]

        # 构建列-聚合函数映射
        func_map = cct.from_list_to_dict(run_col, all_func)
        
        try:
            # 1. 计算 VWAP (nclose)
            if 'close' in run_col:
                vwap_df = self._calc_intraday_vwap_fast(h5, startime, endtime)
                if vwap_df is not None and not vwap_df.empty:
                    dd = cct.combine_dataFrame(dd, vwap_df, col=None, compare=None, append=False, clean=True)
            
            # 2. 聚合极值 (nlow, nhigh)
            agg_cols = [c for c in run_col if c in ['low', 'high']]
            if agg_cols:
                h5_slice = cct.get_limit_multiIndex_Row(h5, col=agg_cols, start=startime, end=endtime)
                if h5_slice is not None and not h5_slice.empty:
                    agg_dict = {}
                    if 'low' in agg_cols: agg_dict['low'] = 'min'
                    if 'high' in agg_cols: agg_dict['high'] = 'max'
                    
                    agg_res = h5_slice.groupby(level=0).agg(agg_dict)
                    agg_res.rename(columns=func_map, inplace=True)
                    dd = cct.combine_dataFrame(dd, agg_res, col=None, compare=None, append=False, clean=True)
            
            log.debug('get_col_agg_df cost:%.2fs' % (time.time() - time_n))
            
        except Exception as e:
            log.error(f"get_col_agg_df Error: {e}")
            
        return dd
        
    def _load_hdf_hist_unified(
        self,
        fname: str = 'sina_MultiIndex_data',
        table: str = None,
        limit_time: Optional[int] = None,
        debug: bool = False
    ) -> pd.DataFrame:
        """
        统一的 HDF5 历史轨迹加载逻辑 (Level 5.5: Flattened Single-Flight IO Loader with Ready Barrier)。
        """
        if table is None:
            table = 'all_' + str(int(cct.sina_limit_time))
        if limit_time is None:
            limit_time = cct.real_time_tick_limit

        cache_key_df = f'unified_h5_hist_{table}'
        cache_key_time = f'unified_h5_hist_time_{table}'
        now_time = time.time()

        # 1. [Memory Cache Check] - 无锁快查
        item = self._MEM_CACHE.get(table)
        if item and item.get('ready'):
            last_t = float(item.get('last_time', 0))
            if not cct.get_work_time_duration() or (now_time - last_t < limit_time):
                return item['df']

        # 2. [Concurrency Control] - 角色分配 (Loader vs Waiter)
        is_loader = False
        event = None
        with self._LOAD_LOCK:
            # 2.1 双检锁 (Double-check inside lock)
            item = self._MEM_CACHE.get(table)
            if item and item.get('ready'):
                last_t = float(item.get('last_time', 0))
                if not cct.get_work_time_duration() or (now_time - last_t < limit_time):
                    return item['df']

            # 2.2 确定角色
            if table in self._LOADING_ST:
                event = self._LOADING_ST[table]
                is_loader = False
            else:
                event = threading.Event()
                self._LOADING_ST[table] = event
                is_loader = True

        if not is_loader:
            # ⚡ [WAITER PATH] - 阻塞并在唤醒后通过 Ready Barrier 验证
            if debug:
                log.info(f"[SingleFlight] Waiter blocking for {table} ...")
            
            event.wait(timeout=60)
            
            # 再次查内存，验证 Ready 标志
            item = self._MEM_CACHE.get(table)
            if item and item.get('ready'):
                return item['df']
            else:
                # 极端情况：非 Ready 状态，返回空交由下轮重试
                return pd.DataFrame()

        # ⚡ [LOADER PATH] - 进入 IO 执行 (Level 6: Production Stable)
        try:
            if debug:
                log.info(f"[SingleFlight] Loader starting IO: {table}")
            
            h5_hist = self.agg_cache.getkey(cache_key_df)
            last_time = self.agg_cache.getkey(cache_key_time)

            need_load = (
                h5_hist is None or 
                last_time is None or 
                (time.time() - float(last_time) > limit_time and cct.get_work_time_duration())
            )

            if need_load:
                with timed_ctx(f"load_h5_{table}", warn_ms=1000):
                    h5_hist = h5a.load_hdf_db(fname, table, timelimit=False, MultiIndex=True)
                
                if h5_hist is not None and not h5_hist.empty:
                    # [OPTIMIZE] 不再使用 agg_cache (GlobalValues) 持久化 172MB 的巨型数据，
                    # 避免在 builtins 中产生双重引用导致无法 GC 内存暴涨。
                    # 统一交由 _MEM_CACHE 和 limit_time 处理 L1 软缓存
                    self.agg_cache.setkey(cache_key_time, time.time())
            
            # ⚡ [1. CACHE WRITE] 先写缓存和 Ready 标志 (确保数据可见性)
            if h5_hist is not None and not h5_hist.empty:
                self._MEM_CACHE[table] = {
                    'df': h5_hist, 
                    'last_time': time.time(),
                    'ready': True 
                }
            
            return h5_hist if h5_hist is not None else pd.DataFrame()

        finally:
            # ⚡ [2. STATE CLEANUP] 先清理加载状态，[3. SIGNAL] 最后唤醒 Waiters
            # 必须在 finally 中单次唤醒，确保 Waiters 醒来时 Loading 状态已同步清理
            with self._LOAD_LOCK:
                if self._LOADING_ST.get(table) == event:
                    del self._LOADING_ST[table]
            event.set() 

    def get_sina_MultiIndex_data(self):
        """兼容性包装：使用统一缓存获取 MultiIndex 数据"""
        return self._load_hdf_hist_unified()

    def clear_unified_cache(self, table: str = None):
        """
        [OPTIMIZATION] 主动清理千万级行的 MultiIndex HDF5 内存缓存。
        专为长时间运行的长驻 UI 进程设计，在回补历史数据完毕后应强制调用此方法释放 500MB+ 的 DataFrame，
        以避免 Python 进程常驻内存偏高。
        """
        table_keys = [table] if table else list(self._MEM_CACHE.keys())
        cleared_any = False
        with self._LOAD_LOCK:
            for k in table_keys:
                if k in self._MEM_CACHE:
                    del self._MEM_CACHE[k]
                    cleared_any = True
        
        if cleared_any:
            log.info(f"🧹 Sina._MEM_CACHE cleared for {table_keys}. Forcing GC...")
            import gc
            gc.collect()

    # def get_code_df_fast(h5_hist: pd.DataFrame, code: str, debug=False) -> pd.DataFrame:
    #     """
    #     从 h5_hist 中筛选指定 code 的行。
    #     支持单索引和多索引，保证返回数据。
    #     """
    #     if code is None:
    #         return h5_hist

    #     try:
    #         df_code = h5_hist.loc[[code]]  # 对 MultiIndex 第一层或单索引都适用
    #         if debug:
    #             print(f"[DEBUG] Found code {code}, rows: {len(df_code)}")
    #         return df_code
    #     except KeyError:
    #         # 没有匹配到返回空 DataFrame
    #         return pd.DataFrame(columns=h5_hist.columns)


    def get_real_time_tick(
        self,
        code: Union[str, List[str]],
        l_limit_time: Optional[int] = None,
        enrich_data: bool = False,
        debug: bool = False
    ) -> pd.DataFrame:
        """
        获取一个或多个股票的实时轨迹 Tick 数据（极限性能版）。
        - 支持批量查询，提高查询效率
        - MultiIndex 高性能过滤
        - 可选增量成交量/成交额处理
        """

        # --- 1. 统一加载 HDF5 历史数据缓存 ---
        h5_hist = self._load_hdf_hist_unified(
            table=None if l_limit_time is None else f'all_{l_limit_time}',
            debug=debug
        )

        if h5_hist.empty:
            return pd.DataFrame()

        # --- 2. 统一 code 列表格式 ---
        codes = [code] if isinstance(code, str) else code
        codes_set = set(codes)

        df_code = pd.DataFrame()

        # --- 3. 高性能过滤 ---
        try:
            if isinstance(h5_hist.index, pd.MultiIndex):
                level0_codes = h5_hist.index.levels[0]
                valid_codes = list(level0_codes.intersection(codes_set))
                if valid_codes:
                    df_code = h5_hist.loc[valid_codes]
            else:
                valid_codes = h5_hist.index.intersection(codes_set)
                if not valid_codes.empty:
                    df_code = h5_hist.loc[valid_codes]
        except Exception as e:
            # 万一极端错误，fallback 最安全方式
            if isinstance(h5_hist.index, pd.MultiIndex):
                df_code = h5_hist.loc[h5_hist.index.get_level_values(0).isin(codes)]
            else:
                df_code = h5_hist.loc[h5_hist.index.isin(codes)]
            if debug:
                log.error(f"[get_real_time_tick fallback] Filter error: {e}")

        if df_code.empty:
            return pd.DataFrame()

        # --- 4. 清洗全零行 (vectorized) ---
        df_code = self.drop_tick_all_zero(df_code)

        # --- 5. 数据增强：增量成交量/成交额 ---
        if enrich_data:
            df_code = self.process_tick_v_a_data(df_code)

        return df_code

    def get_real_time_tick_slow(
        self,
        code: Union[str, List[str]],
        l_limit_time: Optional[int] = None,
        enrich_data: bool = False,
        debug: bool = False
    ) -> pd.DataFrame:
        """
        获取一个或多个股票的实时轨迹 Tick 数据。
        支持批量传入 [code1, code2, ...]，极大提高查询效率。
        """
        # 1. 统一加载 HDF5 (使用架构级共享缓存)
        h5_hist = self._load_hdf_hist_unified(table=None if l_limit_time is None else f'all_{l_limit_time}', debug=debug)

        if h5_hist.empty:
            return pd.DataFrame()

        # 2. 统一代码列表格式
        codes = [code] if isinstance(code, str) else code
        
        # 3. 高性能过滤 (利用 MultiIndex 索引加速)
        df_code = pd.DataFrame()
        try:
            with timed_ctx("sina_data_tick_filter", warn_ms=200):
                if isinstance(h5_hist.index, pd.MultiIndex):
                    # [OPTIMIZE] 如果 codes 较少，使用 .loc 直接定位比 .isin 遍历索引快得多
                    # 假定 MultiIndex 第一层是 code 且已排序
                    valid_codes = [c for c in codes if c in h5_hist.index.levels[0]]
                    if valid_codes:
                        df_code = h5_hist.loc[valid_codes]
                else:
                    valid_codes = [c for c in codes if c in h5_hist.index]
                    if valid_codes:
                        df_code = h5_hist.loc[valid_codes]
        except Exception as e:
            # Fallback to isin for safety if loc fails
            try:
                if isinstance(h5_hist.index, pd.MultiIndex):
                    df_code = h5_hist.loc[h5_hist.index.get_level_values(0).isin(codes)]
                else:
                    df_code = h5_hist.loc[h5_hist.index.isin(codes)]
            except:
                if debug: log.error(f"Filter error for codes {codes}: {e}")

        # 4. 清洗全零行
        if not df_code.empty:
            df_code = self.drop_tick_all_zero(df_code)

        # 5. [NEW] 数据增强：合成增量成交量和成交额
        if enrich_data and not df_code.empty:
            df_code = self.process_tick_v_a_data(df_code)

        return df_code

    def process_tick_v_a_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        [NEW] 增强分时数据：将累积成交量转换为每笔增量，并合成成交额 (Amount/VWAP Basis)。
        支持多日数据：按 code + date 分组计算增量和累计值，解决多日数据成交量断层问题。
        每日的 09:25 - 15:01 数据为一组进行独立转换。
        """
        if df.empty:
            return df

        # 清理 09:25 之前的无效盘前数据
        df_work = df.copy()
        try:
            import datetime as _dt
            cutoff_time = _dt.time(9, 25, 0)
            end_time = _dt.time(15, 0, 1)
            
            # 1. 提取时间戳序列
            if isinstance(df_work.index, pd.MultiIndex):
                # ticktime 通常在第 1 层 (level 1) 或通过名称获取
                tt_val = df_work.index.get_level_values('ticktime') if 'ticktime' in df_work.index.names \
                           else df_work.index.get_level_values(1)
            elif isinstance(df_work.index, pd.DatetimeIndex):
                tt_val = df_work.index
            else:
                # 尝试从常见列获取
                tt_val = df_work.get('ticktime', df_work.get('time', df_work.get('Timestamp')))
            
            # 统一转换为 DatetimeIndex 或 Series[datetime64]
            ts_series = pd.to_datetime(tt_val)
            
            if hasattr(ts_series, 'dt'):
                # 处理 Series
                tt_times = ts_series.dt.time
                mask = (tt_times >= cutoff_time) & (tt_times <= end_time)
                # 提取日期序列用于多日分组
                group_date = ts_series[mask].dt.date.values
            else:
                # 处理 DatetimeIndex
                tt_times = ts_series.time
                mask = (tt_times >= cutoff_time) & (tt_times <= end_time)
                # 提取日期序列
                group_date = ts_series[mask].date
            
            # 2. 过滤有效时段 (09:25 - 15:00)
            df_work = df_work[mask]
            
            if df_work.empty:
                return df_work
        except Exception as e:
            log.warning(f"process_tick_v_a_data: 时间过滤/解析失败: {e}")
            group_date = None

        # 3. 提取股票代码 (确保 code 列存在用于分组)
        if 'code' not in df_work.columns:
            if isinstance(df_work.index, pd.MultiIndex):
                if 'code' in df_work.index.names:
                    df_work = df_work.reset_index('code')
                else:
                    df_work.insert(0, 'code', df_work.index.get_level_values(0))
            else:
                df_work.insert(0, 'code', df_work.index)
        
        # 彻底消除索引名称与列名冲突
        if df_work.index.name == 'code':
            df_work.index.name = None
        if isinstance(df_work.index, pd.MultiIndex) and 'code' in df_work.index.names:
            new_names = [n if n != 'code' else None for n in df_work.index.names]
            df_work.index.names = new_names

        # 识别关键列
        col_vol = 'volume' if 'volume' in df_work.columns else 'vol'
        col_price = 'close' if 'close' in df_work.columns else 'now'
        
        if col_vol not in df_work.columns or col_price not in df_work.columns:
            return df_work

        # 4. 准备分组键 (code + optional date)
        if group_date is not None:
            # 使用临时日期列确保 diff/cumsum 在每日内独立
            df_work['_group_date'] = group_date
            group_keys = ['code', '_group_date']
        else:
            group_keys = ['code']

        # 5. [OPTIMIZE] 极限向量化：替代慢速的 groupby().apply()
        # 计算每笔增量成交量 (tick_vol)
        df_work['tick_vol'] = df_work.groupby(group_keys)[col_vol].diff().fillna(df_work[col_vol]).clip(lower=0)
        
        # 6. 合成成交额与累计成交额
        if 'amount' not in df_work.columns or (df_work['amount'] <= 0).all():
            # 使用临时列计算增量成交额，并通过 df_work.groupby 确保 'code' 等列可见
            df_work['_delta_a'] = df_work['tick_vol'] * df_work[col_price]
            df_work['amount'] = df_work.groupby(group_keys)['_delta_a'].cumsum()
            df_work.drop(columns=['_delta_a'], inplace=True)
        
        # 7. 计算合成均价 (VWAP)
        df_work['avg_price'] = (df_work['amount'] / df_work[col_vol]).fillna(df_work[col_price])
        
        if 'open' not in df_work.columns:
            # 粗略模拟开盘价（如果是分时轨迹）
            df_work['open'] = df_work.groupby(group_keys)[col_price].shift(1).fillna(df_work[col_price])

        # 8. 清理辅助列并恢复索引结构
        if '_group_date' in df_work.columns:
            df_work = df_work.drop(columns=['_group_date'])
            
        df_processed = df_work.set_index('code', append=True).swaplevel()
        return df_processed


    # def get_real_time_tick_old(self, code: str, l_limit_time: int = int(cct.sina_limit_time), debug: bool = False) -> pd.DataFrame:
    #     """
    #     获取指定股票 code 的实时 tick 数据

    #     :param code: 股票代码
    #     :param l_limit_time: 限制时间窗口（分钟），用于选择 HDF5 表名
    #     :param debug: 是否打印调试信息
    #     :return: DataFrame，若没有数据返回空 DataFrame
    #     """
    #     h5_mi_fname = 'sina_MultiIndex_data'
    #     h5_mi_table = 'all_' + str(l_limit_time)
        
    #     # Cache keys including limit_time to distinguish different windows
    #     cache_key_df = f'sina_MultiIndex_hist_{l_limit_time}'
    #     cache_key_time = f'sina_MultiIndex_hist_time_{l_limit_time}'
    #     try:
    #         # 1. Try to load from cache
    #         h5_hist = self.agg_cache.getkey(cache_key_df)
    #         last_time = self.agg_cache.getkey(cache_key_time)
    #         now_time = time.time()
    #         _real_time_tick_limit = cct.real_time_tick_limit
    #         # 2. Check if cache needs update (missing or older than 5 minutes)
    #         if (h5_hist is None or last_time is None) or ((now_time - float(last_time) > _real_time_tick_limit) and cct.get_work_time_duration()):
    #             if debug:
    #                 print(f"[DEBUG] Cache expired or missing. Loading HDF5 from disk: {h5_mi_table}")
    #             # Load HDF5 Data
    #             log.debug(f'load_h5_hist_hdf')
    #             with timed_ctx("sina_data_h5_hist_load_hdf", warn_ms=800):
    #                 h5_hist = h5a.load_hdf_db(h5_mi_fname, h5_mi_table, timelimit=False, MultiIndex=True)
    #             # Update Cache if load successful
    #             if h5_hist is not None and not h5_hist.empty:
    #                 self.agg_cache.setkey(cache_key_df, h5_hist)
    #                 self.agg_cache.setkey(cache_key_time, now_time)
    #         else:
    #             # if debug:
    #                 # log.debug(f"[DEBUG] Using cached HDF5 data (Age: {now_time - float(last_time):.1f}s)")
    #             log.debug(f"[DEBUG] Using cached HDF5 data (Age: {now_time - float(last_time):.1f}s)")

    #         if debug and h5_hist is not None:
    #             print(f"[DEBUG] Table: {h5_mi_table}, rows: {len(h5_hist)}")
            
    #         if h5_hist is None or h5_hist.empty:
    #              return pd.DataFrame()

    #         # 3. Filter for specific code
    #         if code is not None:
    #             with timed_ctx("sina_data_h5_loc_code", warn_ms=800):
    #                 # df_code = get_code_df_fast(h5_hist,code)
    #                 if isinstance(h5_hist.index, pd.MultiIndex):
    #                     if code in h5_hist.index.get_level_values(0):
    #                         df_code = h5_hist.loc[[code]]
    #                         if debug:
    #                             print(f"[DEBUG] Found code {code}, rows: {len(df_code)}")
    #                         return df_code
    #                 elif code in h5_hist.index:
    #                      df_code = h5_hist.loc[[code]]
    #                      return df_code
    #                 return df_code
    #             if debug:
    #                 print(f"[DEBUG] Code {code} not found in {h5_mi_table}")
            
    #         return pd.DataFrame()  # Code not found or hist empty

    #     except FileNotFoundError:
    #         if debug:
    #             print(f"[DEBUG] HDF5 file {h5_mi_fname} not found")
    #         return pd.DataFrame()
    #     except KeyError:
    #         if debug:
    #             print(f"[DEBUG] Table {h5_mi_table} not found in HDF5 file")
    #         return pd.DataFrame()
    #     except Exception as e:
    #         if debug:
    #             print(f"[DEBUG] Unexpected error: {e}")
    #         return pd.DataFrame()


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
    log_level = LoggerFactory.INFO

    log.setLevel(log_level)
    # log.setLevel(LoggerFactory.DEBUG)

    # log.setLevel(LoggerFactory.DEBUG)
    # sina = Sina()
    sina = Sina(readonly=True)
    dm = sina.all


    for ma in ['bj','sh', 'sz', 'cyb', 'kcb']:
        # for ma in ['sh']:
        # df = Sina().market(ma)
        df = sina.market(ma)
        # print df.loc['600581']
        # print len(sina.all)
        print(("market:%s" % (ma)))
        print(f'count:{len(df)}')
    import ipdb;ipdb.set_trace()


    idx_codes = ["000001", "399001", "399006", "000688"]
    # dff = sina.get_stock_list_data(idx_codes, index=True)
    indices_data=[]
    try:
        idf = sina.get_stock_list_data(idx_codes, index=True)
        if idf is not None and not idf.empty:
            nm_map = {"000001": "上证", "999999": "上证", "399001": "深证", "399006": "创业", "999688": "科创", "999312": "科创"}
            for c, r in idf.iterrows():
                p = round((r.now-r.llastp)/r.llastp*100, 2) if r.llastp > 0 else 0.0
                indices_data.append({'name': nm_map.get(str(c), str(c)), 'percent': p})
            _cached_indices_data = indices_data
    except:
        indices_data = []
    print(f'indices_data: {indices_data}')
    import ipdb;ipdb.set_trace()

    for ma in ['bj','sh', 'sz', 'cyb', 'kcb','all']:
        # for ma in ['sh']:
        df = Sina().market(ma)
        # print df.loc['600581']
        # print len(sina.all)
        print(("market:%s" % (ma)))
        print(f'count:{len(df)}')
    import ipdb;ipdb.set_trace()


    # print len(df)
    # code='300107'
    # print sina.get_cname_code('陕西黑猫')
    # print((sina.get_stock_code_data('300502').turnover))
    # print((sina.get_stock_code_data('002190').T))

    # print(sina.get_code_cname('301397'))

    # print(sina.get_code_cname('300107'))
    # df = sina.get_stock_code_data('000017')

    # print((sina.get_stock_code_data('300107').T))
    import ipdb;ipdb.set_trace()
    
    # print df.lastbuy[-5:].to_frame().T
    df = sina.get_stock_list_data(['999999','399001','399006'],index=True)
    code_index = sina.set_stock_codes_index_init(['999999','399001','399006'], True)
    ddd = sina.get_major_indices()
    print(f'get_major_indices: {ddd}')
    print(f'code_index: {code_index}')
    print((df.name))
    # df = sina.get_stock_code_data('999999',index=True)
    print(f'index: {df}')
    code='603056'
    code='300058'
    # dd = sina.get_real_time_tick('300376')
    dd = sina.get_real_time_tick(code)
    dde = sina.get_real_time_tick(code, enrich_data=True)
    import ipdb;ipdb.set_trace()

    tickdf = cct.tick_to_daily_bar(dd)
    print(f'cct.sina_MultiIndex_startTime: {cct.sina_MultiIndex_startTime} dd:{dd[-3:]}')
    df =sina.all
    print(f'ticktime: {df.ticktime[:5]}')    
    import ipdb;ipdb.set_trace()
    # print(df.loc['920274'][['close','nclose','nlow','nhigh']])
    # print(df.loc['920274'][['close','nclose','nlow','nhigh']])
    print(df.loc['601698'].nclose)
    print(df.loc['601698'].close)
    
    print(df[['close','nclose','nlow','nhigh']])
    print(f"df.loc['002786']: {df.loc['002786']}")
    print((df[-5:][['open','close']].T))
    print(f'总计: {len(df)}')
    dm = df
    stop_code = dm[~((dm.b1 > 0) | (dm.a1 > 0) | (dm.buy >0) | (dm.sell >0))].loc[:,['name']].T
    print(f'总计: {len(df)} 停牌个股stop_code:{len(stop_code)} \n {stop_code}')
    import ipdb;ipdb.set_trace()

    for ma in ['bj','sh', 'sz', 'cyb', 'kcb','all']:
        # for ma in ['sh']:
        df = Sina().market(ma)
        # print df.loc['600581']
        # print len(sina.all)
        print(("market:%s" % (ma)))
        print(f'count:{len(df)}')

        

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
    code_agg = '601939'
    dd = sina.get_stock_code_data([code_agg,'600050','002350', '601899',\
      '603363','000868','603917','600392','300713','000933','002505','603676'])
    print((dd.T))

    print((dd.loc[:, ['name','open','low','high','close', 'ticktime']], dd.shape))
    # print((dd.loc[:, ['name','open','low','high','close', 'nclose', 'nlow', 'nhigh', 'nstd', 'ticktime']], dd.shape))

    
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
                h5 = h5.groupby(level=0).last()
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
    # h5_table = 'all_10'
    h5_table = 'all' + '_' + str(cct.sina_limit_time)
    time_s = time.time()

    h5 = h5a.load_hdf_db(h5_fname, table=h5_table, code_l=None, timelimit=False, dratio_limit=0.12)
    print(('h5:', len(h5)))
    import ipdb;ipdb.set_trace()

    if cct.get_trade_date_status() and cct.get_now_time_int() <= 945:
        run_col = ['low', 'high', 'close']
        startime = None
        # endtime = '10:00:00'
        endtime = '09:45:00'
        dd = get_col_agg_df_Test(h5, dd, run_col, all_func, startime, endtime)
    else:
        run_col = ['low', 'high']
        startime = None
        # endtime = '10:00:00'
        endtime = '09:35:00'
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
        # readonly 检查
        if hasattr(self, 'readonly') and self.readonly:
            print("Readonly mode: skip write_hdf_db")
        else:
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
