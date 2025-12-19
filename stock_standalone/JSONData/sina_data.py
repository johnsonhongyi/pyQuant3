# -*- encoding: utf-8 -*-
import json
import os
import re
import sys
import time

sys.path.append("..")
import pandas as pd
import numpy as np
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
# from akshare import stock_info_bj_name_code
# pip install --no-deps akshare
# import functools
import datetime

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

def get_stock_code_path():
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
        if os.path.getsize(default_path) > 0:
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

    def __init__(self):
        self.start_t = time.time()
        # self.STOCK_CODE_PATH = os.path.join(BASE_DIR,"stock_codes.conf")
        self.STOCK_CODE_PATH = get_stock_code_path()
        if not self.STOCK_CODE_PATH:
            log.critical("stock_codes.conf 加载失败，程序无法继续运行")

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

    # @property
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
        stock_codes = list(set([elem for elem in stock_codes if elem.startswith(('60', '30', '00','688','43','83','87','92'))]))
        # df=rl.get_sina_Market_json('all')
        # stock_codes = df.index.tolist()
        # '301397'
        # stock_info_bj_name_code_df = stock_info_bj_name_code()
        # bj_list = stock_info_bj_name_code_df['证券代码'].tolist(
        # stock_codes.extend(bj_list)
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
        self.hdf_name = 'sina_data'
        self.table = 'all'
        self.sina_limit_time = cct.sina_limit_time
        pd.options.mode.chained_assignment = None
        self.cname = False
        self.encoding = 'gbk'
        self.sinaheader = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0',
            'referer': 'http://finance.sina.com.cn',
            'Connection': 'keep-alive',
            }
        self.agg_cache = cct.GlobalValues() # 用于聚合缓存

    def get_int_time(self,timet):
        return int(time.strftime("%H:%M:%S",time.localtime(timet))[:6].replace(':',''))

    def load_stock_codes(self, all_codes=None):
        if all_codes is not None:
            self.stock_codes = list(set(all_codes))
        else:
            with open(self.stock_code_path) as f:
                self.stock_codes = list(set(json.load(f)['stock']))
        
        # 统一内存级别剔除停牌股
        excluded_codes = cct.GlobalValues().getkey('suspended_codes') or []
        if excluded_codes:
            original_len = len(self.stock_codes)
            self.stock_codes = [c for c in self.stock_codes if c not in excluded_codes]
            if len(self.stock_codes) < original_len:
                log.info(f"Session过滤停牌/无效股: {original_len - len(self.stock_codes)} 只")

    def _filter_suspended(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        统一检测并剔除停牌/无效股票，并更新内存缓存
        """
        if df is None or len(df) == 0:
            return df
            
        # 集合竞价期间(09:15-09:25)不进行无效股剔除，因为此时价格/成交量可能为0但属于正常状态
        if 915 <= cct.get_now_time_int() <= 925:
             return df
            
        # 判定条件：open, now 均为 0 表示停牌或无效。
        # 注意：format_response_data 中已将原始 close 映射为 llastp，并将 now 映射为新 close。
        # 因此 query 使用 close==0 or now==0 均可。
        query_str = 'open == 0 and now == 0'
        if 'close' in df.columns:
            query_str = 'open == 0 and close == 0 and now == 0'
            
        suspended = df.query(query_str)
        if len(suspended) > 0:
            new_suspended = suspended.index.tolist()
            log.info(f"检测到停牌股/无效数据: {len(new_suspended)} 只, 内存已记录并剔除")
            excluded = cct.GlobalValues().getkey('suspended_codes') or []
            excluded.extend(new_suspended)
            cct.GlobalValues().setkey('suspended_codes', list(set(excluded)))
            df = df.drop(new_suspended)
        return df

    @property
    def all(self) -> pd.DataFrame:
        """获取所有实时数据 (优化 HDF5 加载逻辑)"""
        self.stockcode = StockCode()
        self.stock_code_path = self.stockcode.stock_code_path
        all_codes = self.stockcode.get_stock_codes()
        self.load_stock_codes(all_codes)
        time_s = time.time()
        
        # 1. 尝试从 HDF5 加载历史数据
        sina_limit_time_val: int = int(self.sina_limit_time) if self.sina_limit_time is not None else 60
        h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=self.stock_codes, limit_time=sina_limit_time_val)
        
        if h5 is not None and len(h5) > 0:
            # 基础预处理
            if 'ticktime' in h5.columns:
                # 检查 ticktime 是否有效
                valid_tick = h5[h5.ticktime != 0].ticktime
                if len(valid_tick) > 0:
                    o_time = valid_tick
                    otime = h5.ticktime
                    ticktime_val = o_time.iloc[0]
                    
                    if isinstance(ticktime_val, str):
                        ts_str = ticktime_val.replace(":", "")[-6:]
                    else:
                        ts_str = str(ticktime_val)[-6:]
                    
                    try:
                        ticktime_int = int(ts_str)
                    except ValueError:
                        ticktime_int = 0
                        
                    if ticktime_int > 0:
                        # 重构 l_time 计算逻辑 (简化版)
                        now_dt = datetime.datetime.now()
                        try:
                            if ':' in str(ticktime_val):
                                h, m, s = map(int, str(ticktime_val).split(':'))
                                last_dt = now_dt.replace(hour=h, minute=m, second=s)
                            else:
                                ts_s = str(ticktime_val).zfill(6)
                                last_dt = now_dt.replace(hour=int(ts_s[:2]), minute=int(ts_s[2:4]), second=int(ts_s[4:6]))
                            l_time = (now_dt - last_dt).total_seconds()
                            if l_time < 0:
                                # 若时间在未来 (跨天)，视为旧数据
                                l_time = 99999
                        except Exception:
                            l_time = 99999
                            
                        # 显式转换为 int 以消除类型警告
                        sina_limit_time_int: int = int(cct.sina_limit_time) if cct.sina_limit_time is not None else 60
                        sina_time_status = (cct.get_work_day_status() and 915 < cct.get_now_time_int() < 926)
                        
                        # 确保 get_work_time 接收显式 bool 或 None
                        work_time_now = cct.get_work_time()
                        return_hdf_status = (not work_time_now) or (cct.get_trade_date_status() and l_time < sina_limit_time_int)
                        
                        log.debug("HDF5 check: sina_time_status=%s, l_time=%0.2f, limit=%s", sina_time_status, l_time, sina_limit_time_int)
                        
                        # 若数据足够新，则直接合并 lastbuy 并返回
                        # 增加校验：如果 nlow/nhigh 出现 0.0，说明 HDF5 数据质量差，强制刷新
                        hdf_data_valid = True
                        if h5 is not None and not h5.empty:
                            for c_check in ['nlow', 'nhigh']:
                                if c_check in h5.columns:
                                    zero_ratio = (h5[c_check] <= 0).sum() / len(h5)
                                    if zero_ratio > 0.1: # 超过 10% 是 0，视为脏数据
                                        hdf_data_valid = False
                                        log.warning("HDF5 data quality poor (zero_ratio of %s: %.2f), bypassing early return" % (c_check, zero_ratio))
                                        break
                        
                        if hdf_data_valid and ((sina_time_status and l_time < 6) or (not sina_time_status and return_hdf_status)):
                            log.info("Return HDF5 data early (recent:%0.2f)" % l_time)
                            # 兼容转成 HH:MM:SS 格式
                            if h5 is not None and not h5.empty and 'ticktime' in h5.columns:
                                 h5.loc[:, 'ticktime'] = h5['ticktime'].astype(str).apply(lambda x: x if ':' in x else f"{x.zfill(6)[:2]}:{x.zfill(6)[2:4]}:{x.zfill(6)[4:6]}")
                            return self._sanitize_indicators(self.combine_lastbuy(h5))

            # 若不可早退，继续后续流程
            log.info("HDF5 exists but not recent enough (%d rows)" % len(h5))
        else:
            log.info("HDF5 data missing or empty")

        # 2. 从网络获取最新数据
        self.stock_with_exchange_list = [cct.code_to_symbol(code) for code in self.stock_codes]
        
        # 补回分片请求逻辑
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
        
        if df is None or len(df) == 0:
            log.warning("Failed to fetch fresh data from Sina")
            return self._filter_suspended(h5) if h5 is not None else pd.DataFrame()

        # 3. 确定是否需要从历史轨迹重建 (Anytime Recovery)
        agg_data = self.agg_cache.getkey('agg_metrics')
        cache_needs_rebuild = False
        if agg_data is None or agg_data.empty:
            cache_needs_rebuild = True
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
        if cache_needs_rebuild:
            log.info("AggregatorCache poor or missing, rebuilding from MultiIndex HDF5...")
            l_limit_time = int(cct.sina_limit_time)
            h5_mi_fname = 'sina_MultiIndex_data'
            h5_mi_table = 'all_' + str(l_limit_time)
            h5_hist = h5a.load_hdf_db(h5_mi_fname, h5_mi_table, timelimit=False)
            df_final = self._rebuild_agg_cache(h5_hist, df)
            # 此时内存缓存已由 _rebuild_agg_cache 设置好
        else:
            # 正常更新逻辑：先更新增量，再合并
            self._update_agg_cache(df)
            agg_data = self.agg_cache.getkey('agg_metrics')
            df_final = cct.combine_dataFrame(df, agg_data)

        # 5. 合并 lastbuy 并持久化
        df_final = self.combine_lastbuy(df_final)
        # 使用 index=False 避免反转索引，且先 copy 避免影响返回的对象
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
            if cct.get_work_time():
                # 构造 MultiIndex 精简格式轨迹: [code, ticktime, close, high, low, llastp, volume, lastbuy]
                # 这必须与 format_response_data 中的 mi_cols 保持绝对一致以避免 ValueError
                mi_cols = ['code', 'ticktime', 'close', 'high', 'low', 'llastp', 'volume', 'lastbuy']
                mi_df = df_final.loc[:, [c for c in mi_cols if c in df_final.columns]].copy()
                
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
                    h5a.write_hdf_db(h5_mi_fname, mi_df, table=h5_mi_table, index=True, MultiIndex=True)
                    self.agg_cache.setkey('last_mi_save_time', now_time)
                    log.info("Saved MultiIndex history (sync) to %s cols:%s" % (h5_mi_fname, mi_df.columns.tolist()))

        return self._filter_suspended(df_final)

    def _update_agg_cache(self, df_latest: pd.DataFrame) -> None:
        """增量更新内存中的聚合指标 (带时间窗口控制)"""
        if df_latest is None or len(df_latest) == 0:
            return
            
        agg_metrics: pd.DataFrame | None = self.agg_cache.getkey('agg_metrics')
        
        # 1. 提取当前批次的统计值
        stats: pd.DataFrame
        if 'code' in df_latest.columns:
            stats = df_latest.groupby('code').agg({'low': 'min', 'high': 'max', 'close': 'last'})
        else:
            stats = df_latest.groupby(level=0).agg({'low': 'min', 'high': 'max', 'close': 'last'})
            
        # 强制索引为字符串
        stats.index = stats.index.astype(str)
        
        # 容错：如果 low/high 为 0，使用 close 兜底
        stats.loc[stats['low'] <= 0, 'low'] = stats['close']
        stats.loc[stats['high'] <= 0, 'high'] = stats['close']

        if agg_metrics is None:
            new_agg = stats.rename(columns={'low': 'nlow', 'high': 'nhigh', 'close': 'nclose'})
            new_agg.index = new_agg.index.astype(str)
            new_agg['nstd'] = np.nan
            self.agg_cache.setkey('agg_metrics', new_agg)
            log.info("Initialized AggregatorCache with %d codes" % len(new_agg))
            return
            
        if not agg_metrics.index.dtype == object:
             agg_metrics.index = agg_metrics.index.astype(str)
            
        now_int = cct.get_now_time_int()
        
        common_codes = agg_metrics.index.intersection(stats.index)
        if len(common_codes) > 0:
            # nlow: 强制修正 0.0 或 NaN
            agg_metrics.loc[common_codes, 'nlow'] = agg_metrics.loc[common_codes, 'nlow'].fillna(0)
            idx_low_fix = (agg_metrics.loc[common_codes, 'nlow'] <= 0)
            if idx_low_fix.any():
                fix_codes = common_codes[idx_low_fix]
                agg_metrics.loc[fix_codes, 'nlow'] = stats.loc[fix_codes, 'low']
                
            if now_int <= 945:
                 agg_metrics.loc[common_codes, 'nlow'] = agg_metrics.loc[common_codes, 'nlow'].combine(stats.loc[common_codes, 'low'], min)

            # nhigh: 强制修正 0.0 或 NaN
            agg_metrics.loc[common_codes, 'nhigh'] = agg_metrics.loc[common_codes, 'nhigh'].fillna(0)
            idx_high_fix = (agg_metrics.loc[common_codes, 'nhigh'] <= 0)
            if idx_high_fix.any():
                fix_codes_h = common_codes[idx_high_fix]
                agg_metrics.loc[fix_codes_h, 'nhigh'] = stats.loc[fix_codes_h, 'high']

            if now_int <= 1030:
                 agg_metrics.loc[common_codes, 'nhigh'] = agg_metrics.loc[common_codes, 'nhigh'].combine(stats.loc[common_codes, 'high'], max)

            agg_metrics.loc[common_codes, 'nclose'] = stats.loc[common_codes, 'close']

        new_codes = stats.index.difference(agg_metrics.index)
        if len(new_codes) > 0:
            new_df = stats.loc[new_codes].rename(columns={'low': 'nlow', 'high': 'nhigh', 'close': 'nclose'})
            # 补齐：防止新 code 出现 0.0
            new_df.loc[new_df['nlow'] <= 0, 'nlow'] = stats.loc[new_codes, 'close']
            new_df.loc[new_df['nhigh'] <= 0, 'nhigh'] = stats.loc[new_codes, 'close']
            agg_metrics = pd.concat([agg_metrics, new_df])
            
        self.agg_cache.setkey('agg_metrics', agg_metrics)

    def _rebuild_agg_cache(self, h5_hist, df_current):
        """从历史 MultiIndex 数据中重建聚合缓存 (优化兼容日期前缀)"""
        time_s = time.time()
        if h5_hist is not None and not h5_hist.empty:
            if not isinstance(h5_hist.index, pd.MultiIndex):
                 h5_hist = h5_hist.set_index(['code', 'ticktime'], append=False)
            
            # 提取时间部分 HH:MM:SS，兼容 '2025-12-18 09:25:00' 格式
            tick_times = h5_hist.index.get_level_values('ticktime').astype(str)
            time_only = tick_times.str.split().str[-1]
            
            agg_low = h5_hist[time_only <= '09:45:00'].groupby(level=0)['low'].min().to_frame('nlow')
            agg_high = h5_hist[time_only <= '10:30:00'].groupby(level=0)['high'].max().to_frame('nhigh')
            agg_close = h5_hist.groupby(level=0)['close'].last().to_frame('nclose')
            
            h5_std = h5_hist[(time_only >= '09:25:00') & (time_only <= '09:35:00')]
            if not h5_std.empty:
                agg_std = h5_std.groupby(level=0)['close'].std().to_frame('nstd').round(2)
            else:
                agg_std = pd.DataFrame(columns=['nstd'])
            agg_df = pd.concat([agg_low, agg_high, agg_close, agg_std], axis=1)
        else:
            agg_df = pd.DataFrame(columns=['nlow', 'nhigh', 'nclose', 'nstd'])

        if 'code' in df_current.columns:
            curr_stats = df_current.groupby('code').agg({'low': 'min', 'high': 'max', 'close': 'last'})
        else:
            curr_stats = df_current.groupby(level=0).agg({'low': 'min', 'high': 'max', 'close': 'last'})
            
        # 统一索引类型为字符串
        agg_df.index = agg_df.index.astype(str)
        curr_stats.index = curr_stats.index.astype(str)
        
        all_codes = agg_df.index.union(curr_stats.index)
        rebuild_df = pd.DataFrame(index=all_codes)
        rebuild_df.index = rebuild_df.index.astype(str)
        now_int = cct.get_now_time_int()

        # nlow: 优先使用历史记录，修正 0.0 或 NaN
        rebuild_df['nlow'] = agg_df['nlow'].reindex(rebuild_df.index).fillna(0)
        idx_low_fix = (rebuild_df['nlow'] <= 0)
        if idx_low_fix.any():
            codes_fix = rebuild_df.index[idx_low_fix]
            rebuild_df.loc[codes_fix, 'nlow'] = curr_stats['low'].reindex(codes_fix).fillna(0)
            # 二次兜底
            idx_still_zero = (rebuild_df.loc[codes_fix, 'nlow'] <= 0)
            if idx_still_zero.any():
                 codes_still = codes_fix[idx_still_zero]
                 rebuild_df.loc[codes_still, 'nlow'] = curr_stats['close'].reindex(codes_still)
        
        if now_int <= 945:
            rebuild_df['nlow'] = rebuild_df['nlow'].combine(curr_stats['low'].reindex(rebuild_df.index), min)
            
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
        
        if now_int <= 1030:
            rebuild_df['nhigh'] = rebuild_df['nhigh'].combine(curr_stats['high'].reindex(rebuild_df.index), max)
            
        # nclose: 直接用当前价更新
        rebuild_df['nclose'] = curr_stats['close'].reindex(rebuild_df.index).fillna(agg_df['nclose'].reindex(rebuild_df.index))
        # 三次兜底：确保 nclose 不为 0
        rebuild_df.loc[rebuild_df['nclose'] <= 0, 'nclose'] = curr_stats['close'].reindex(rebuild_df.index)
        
        if 'nstd' in agg_df.columns:
             rebuild_df['nstd'] = agg_df['nstd'].reindex(rebuild_df.index)
        else:
             rebuild_df['nstd'] = np.nan

        self.agg_cache.setkey('agg_metrics', rebuild_df)
        log.info("Rebuild agg cache. size:%s time:%.2f" % (len(rebuild_df), time.time() - time_s))
        return cct.combine_dataFrame(df_current, rebuild_df)


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
            all_codes = self.stockcode.get_stock_codes()
            self.load_stock_codes(all_codes)
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
                    [('sh%s') % stock_code for stock_code in self.stock_codes])
            elif market == 'bj':
                # self.stock_codes = [elem for elem in self.stock_codes if elem.startswith('43') or elem.startswith('83') or elem.startswith('87') or elem.startswith('92')]
                self.stock_codes = [elem for elem in self.stock_codes if elem.startswith(('43','83','87','92'))]
                self.stock_with_exchange_list = list(
                    [('bj%s') % stock_code for stock_code in self.stock_codes])
            self.stock_codes = list(set(self.stock_codes))

            time_s= time.time()
            
            h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=self.stock_codes, limit_time=int(self.sina_limit_time))
            # h5[:1].ticktime.values[0][-8:-3].replace(":",'')
            log.info("h5a market: %s stocksTime:%0.2f" % (market,time.time() - time_s))

            if h5 is not None and len(h5) > 0:
                o_time = h5[h5.timel != 0].timel

                # 获取第一个非零 ticktime
                ts = h5[h5.ticktime != 0].ticktime.iloc[0]  # iloc[0] 更安全
                if isinstance(ts, pd.Timestamp):
                    ts_str = ts.strftime('%H%M%S')  # 转成 'HHMMSS'
                elif isinstance(ts, datetime.datetime):
                    ts_str = ts.strftime('%H%M%S')
                elif isinstance(ts, str):
                    # 如果已经是字符串，尝试去掉冒号或处理已有格式
                    ts_str = ts.replace(":", "")[-6:]  # 保留 HHMMSS
                else:
                    # 其他类型直接转字符串
                    ts_str = str(ts)[-6:]

                ticktime = int(ts_str)
                # ticktime = int(h5[h5.ticktime != 0].ticktime[0][-8:-3].replace(":",''))

                if len(o_time) > 0 and ((self.get_int_time(o_time[0]) >= 1500 and ticktime >= 1500) or (self.get_int_time(o_time[0]) < 1500 and ticktime < 1500) ):
                    h5 = self.combine_lastbuy(h5)
                    return self._filter_suspended(h5)

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
            return self._filter_suspended(self.get_stock_data())


    # https://github.com/jinrongxiaoe/easyquotation
    async def get_stocks_by_range(self, index):

        url = self.sina_stock_api + self.stock_list[index]
        async with aiohttp.ClientSession() as session:
                response = await session.get(url=url,headers=self.sinaheader)
                headers = response.headers
                response.encoding = self.encoding
                result = await response.text()
                await session.close()
                # print(u, headers)
                # return headers


        self.stock_data.append(result)

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
            
            df = self.format_response_data()
            return self._filter_suspended(df)

        raise IOError(ct.NETWORK_URL_ERROR_MSG)


    def lastbuy_timeout_status(self,logtime):

        return (time.time() - float(logtime) > float(ct.sina_lastbuy_logtime))

    def combine_lastbuy(self, h5: pd.DataFrame) -> pd.DataFrame:
        """合并上次买入价格与聚合指标 (优化版：彻底移除热路径 HDF5 加载)"""
        time_s = time.time()
        
        # 1. 基础预处理 (不再全局 fillna(0))
        if 'lastbuy' in h5.columns:
             h5.loc[:, 'lastbuy'] = h5['lastbuy'].fillna(0)
        
        # 2. 检查 lastbuy (优先使用内存中的 lastbuydf)
        if 'lastbuy' not in h5.columns or (h5['lastbuy'] <= 0).any():
            lastbuydf = cct.GlobalValues().getkey('lastbuydf')
            if lastbuydf is not None:
                # 对齐索引并合并
                if isinstance(h5.index, pd.MultiIndex):
                    codes = h5.index.get_level_values(0)
                    h5['lastbuy'] = lastbuydf.reindex(codes).values
                else:
                    h5['lastbuy'] = lastbuydf.reindex(h5.index).values
            else:
                # 如果全局缓存也没有，则作为兜底逻辑尝试从指标缓存中提取
                agg_metrics = self.agg_cache.getkey('agg_metrics')
                if agg_metrics is not None and 'nclose' in agg_metrics.columns:
                     if isinstance(h5.index, pd.MultiIndex):
                         codes = h5.index.get_level_values(0)
                         h5['lastbuy'] = agg_metrics.reindex(codes)['nclose'].values
                     else:
                         h5['lastbuy'] = agg_metrics.reindex(h5.index)['nclose'].values
                     log.debug("lastbuy from agg_metrics")
        
        # 3. 检查聚合指标 (nclose, nstd, nlow, nhigh)
        # 只要存在 0 值且缓存有数据，就进行合并更新
        if 'nclose' not in h5.columns or (h5['nclose'] <= 0).any():
             agg_metrics = self.agg_cache.getkey('agg_metrics')
             if agg_metrics is not None:
                 h5 = cct.combine_dataFrame(h5, agg_metrics)
                 
        # 4. 强制清洗指标，杜绝 0.0
        h5 = self._sanitize_indicators(h5)

        time_use = round((time.time() - time_s), 2)
        if time_use > 0.5:
             log.info("combine_lastbuy (cache) time: %0.2f" % time_use)
             
        return h5

    def _sanitize_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一清洗指标列中的 0.0 或 NaN 值，确保所有返回的数据都是健康的"""
        if df is None or df.empty:
            return df
        
        # 强制索引转为字符串 (兼容 MultiIndex)
        if isinstance(df.index, pd.MultiIndex):
            for i in range(df.index.nlevels):
                if not df.index.levels[i].dtype == object:
                     df.index = df.index.set_levels(df.index.levels[i].astype(str), level=i)
        else:
            if not df.index.dtype == object:
                df.index = df.index.astype(str)
            
        # 目标列及其兜底列
        targets = [('nlow', 'low'), ('nhigh', 'high'), ('nclose', 'close'), ('lastbuy', 'close')]
        for target, fallback in targets:
            if target in df.columns:
                # 填充 NaN 为 0，方便统一判断
                df.loc[:, target] = df[target].fillna(0).values
                
                # 1. 基础修正 (针对 0.0)
                mask = (df[target] <= 0)
                if mask.any():
                    if fallback in df.columns:
                         df.loc[mask, target] = df.loc[mask, fallback].fillna(0).values
                    
                    mask_still = (df[target] <= 0)
                    if mask_still.any() and 'close' in df.columns:
                         df.loc[mask_still, target] = df.loc[mask_still, 'close']

                # 2. 一致性修正 (确保 nlow 不大于 low, nhigh 不小于 high)
                if target == 'nlow' and 'low' in df.columns:
                     # 如果 nlow 反而比今日最低价还高，说明指标由于某种原因落后或初始化错误，强制同步
                     mask_invalid = (df['nlow'] > df['low']) & (df['low'] > 0)
                     if mask_invalid.any():
                          df.loc[mask_invalid, 'nlow'] = df.loc[mask_invalid, 'low']
                          
                elif target == 'nhigh' and 'high' in df.columns:
                     # 如果 nhigh 反而比今日最高价还低，强制同步
                     mask_invalid_h = (df['nhigh'] < df['high']) & (df['high'] > 0)
                     if mask_invalid_h.any():
                          df.loc[mask_invalid_h, 'nhigh'] = df.loc[mask_invalid_h, 'high']

        # 处理 nstd
        if 'nstd' in df.columns:
            df.loc[df['nstd'].fillna(0) <= 0, 'nstd'] = np.nan
            
        return df

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
            self.stock_codes = [(
                'sh%s' if stock_code.startswith(('0')) else 'sz%s') % stock_code for stock_code in code_l]

        else:
            code_l = code
            self.stock_codes = [cct.code_to_symbol(stock_code) for stock_code in code_l]
        return code_l

    def get_stock_code_data(self, code, index=False):

        code_l = self.set_stock_codes_index_init(code, index)
        h5 = h5a.load_hdf_db(self.hdf_name, self.table, code_l=code_l, index=index, limit_time=int(self.sina_limit_time))
        if h5 is not None:
            log.info("find index hdf5 data:%s" % (len(h5)))
            h5 = self.combine_lastbuy(h5)
            return h5
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
            self.stock_list = []
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
                self.stock_codes = [ cct.code_to_symbol(stock_code)  for stock_code in ulist]

            if len(self.stock_codes) == 0:
                log.error("self.stock_codes is None:%s"%(self.stock_codes))
            self.url = self.sina_stock_api + ','.join(self.stock_codes)
            log.info("stock_list:%s" % self.url[:30])
            response = requests.get(self.url,headers=self.sinaheader)
            response.encoding = self.encoding
            self.stock_data.append(response.text)
            self.dataframe = self.format_response_data(index)
        return self.dataframe

    def get_col_agg_df(self, h5, dd, run_col, all_func, startime, endtime, freq=None):
        """
        聚合 MultiIndex DataFrame，按 code 聚合 ticktime。
        h5: 原始 tick 数据
        dd: 已存在的汇总数据
        run_col: 需要聚合的列列表或字典
        all_func: 所有列的聚合映射
        startime, endtime: 切片时间
        freq: 可选，按频率取最后一条
        """

        if isinstance(run_col, list):
            now_col = [all_func[co] for co in run_col if co in all_func]
        else:
            now_col = [all_func[co] for co in run_col.keys() if co in all_func]

        # 构建列-聚合函数映射
        func_map = cct.from_list_to_dict(run_col, all_func)

        if h5 is not None and len(h5) > len(dd):
            time_n = time.time()

            # 先切片时间
            if freq is None:
                h5 = cct.get_limit_multiIndex_Row(h5, col=run_col, start=startime, end=endtime)
            else:
                # 如果按 freq，只取每组最后一条（更高效方式）
                h5 = cct.get_limit_multiIndex_freq(h5, freq=freq, col=run_col, start=startime, end=endtime)
                h5 = h5.groupby(level=0).last()

            if h5 is not None and len(h5) > 0:
                # 重置 index 到 code
                h5 = h5.reset_index().set_index('code')
                h5.rename(columns=func_map, inplace=True)
                h5 = h5.loc[:, now_col]

                # 使用 combine_dataFrame 合并
                dd = cct.combine_dataFrame(dd, h5, col=None, compare=None, append=False, clean=True)

            log.info('agg_df_Row:%.2f s, h5:%s, endtime:%s' % ((time.time() - time_n), len(h5), endtime))

        return dd

    def format_response_data(self, index=False):
        stocks_detail = ''.join(self.stock_data)
        # print stocks_detail
        result = self.grep_stock_detail.finditer(stocks_detail)
        # stock_dict = dict()
        list_s = []
        for stock_match_object in result:
            stock = stock_match_object.groups()
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
        dt = df.dt.value_counts().index[0]
        df = df[(df.dt >= dt)]

        df.rename(columns={'close': 'llastp'}, inplace=True)
        df['b1_vv'] = df['b1_v'].map(lambda x: int(x/100/10000))
        if (cct.get_now_time_int() > 915 and cct.get_now_time_int() < 926):
            df['close'] = df['buy']
            df['open'] = df['buy']
            # 仅在现值为 0 或 NaN 时才使用 buy 竞价，保护已有极值
            idx_low = (df['low'] <= 0) | (df['low'].isna())
            df.loc[idx_low, 'low'] = df.loc[idx_low, 'buy']
            idx_high = (df['high'] <= 0) | (df['high'].isna())
            df.loc[idx_high, 'high'] = df.loc[idx_high, 'buy']
            df['volume'] = ((df['b1_v'] + df['b2_v'])).map(lambda x: x)

        elif (cct.get_now_time_int() > 0 and cct.get_now_time_int() <= 915):
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
            df.index = list(map((lambda x: str(1000000 - int(x))
                            if x.startswith('0') else x), df.index))
        log.info("hdf:all%s %s" % (len(df), len(self.stock_codes)))
        dd = df.copy()
        h5_fname = 'sina_MultiIndex_data'
        h5_table = 'all' + '_' + str(cct.sina_limit_time)
        fname = 'sina_logtime'
        logtime = cct.get_config_value_ramfile('sina_logtime')
        otime =  cct.get_config_value_ramfile('sina_logtime',int_time=True)

        if cct.get_now_time_int() > 925 and (not index and len(df) > 3000 and ( cct.get_work_time(otime) or cct.get_work_time())):
            time_s = time.time()
            df.index = df.index.astype(str)
            df.ticktime = df.ticktime.astype(str)
            df.ticktime = list(map(lambda x, y: str(x) + ' ' + str(y), df.dt, df.ticktime))
            df.ticktime = pd.to_datetime(df.ticktime, format='%Y-%m-%d %H:%M:%S')

            if logtime == 0:
                duratime = cct.get_config_value_ramfile(fname,currvalue=time.time(),xtype='time',update=True)
                df['lastbuy'] = (list(map(lambda x, y: y if int(x) == 0 else x,
                                          df['close'].values, df['llastp'].values)))
                cct.GlobalValues().setkey('lastbuydf', df['lastbuy']) 

            else:
                
                if (cct.GlobalValues().getkey('lastbuylogtime') is not None ) or self.lastbuy_timeout_status(logtime):
                    duratime = cct.get_config_value_ramfile(fname,currvalue=time.time(),xtype='time',update=True)
                    df['lastbuy'] = (list(map(lambda x, y: y if int(x) == 0 else x,
                                              df['close'].values, df['llastp'].values)))
                    cct.GlobalValues().setkey('lastbuylogtime', None) 
                    cct.GlobalValues().setkey('lastbuydf', df['lastbuy']) 
                else:
                    df = self.combine_lastbuy(df)
            #top_temp.loc['600903'][['lastbuy','now']]
            #spp.all_10.lastbuy.groupby(level=[0]).tail(1).reset_index().set_index('code')[-50:]
            dd = df.copy()
            # --- 分别处理轨迹数据(mi)和实时数据(dd) ---
            # 1. 轨迹历史数据 (仅精简 8 列) -> sina_MultiIndex_data.h5
            # 注意: 使用独立的 df_mi 对象，避免干扰后续对 dd 的处理
            df_mi = df.copy()
            if 'code' not in df_mi.columns:
                df_mi = df_mi.reset_index()
            
            mi_cols = ['code', 'ticktime', 'close', 'high', 'low', 'llastp', 'volume', 'lastbuy']
            if 'lastbuy' not in df_mi.columns:
                df_mi['lastbuy'] = df_mi['close'] if 'close' in df_mi.columns else 0
            
            # 严格筛选列，多余的不要
            df_mi_write = df_mi.loc[:, [c for c in mi_cols if c in df_mi.columns]]
            
            # 存储前确保 'code' 和 'ticktime' 形成 MultiIndex，防止 write_hdf_db(index=False) 导致主键丢失
            # 严格使用 MultiIndex + index=True 模式，以兼容 tdx_hdf5_api 的读取对比逻辑
            if isinstance(df_mi_write.index, pd.RangeIndex):
                if 'code' in df_mi_write.columns and 'ticktime' in df_mi_write.columns:
                     df_mi_write = df_mi_write.set_index(['code', 'ticktime'])
            
            h5_mi_fname = 'sina_MultiIndex_data'
            limit_time_int = int(self.sina_limit_time) if self.sina_limit_time else 60
            h5_mi_table = 'all_' + str(limit_time_int)
            
            # 使用 index=True 强制保存索引
            h5a.write_hdf_db(h5_mi_fname, df_mi_write, table=h5_mi_table, index=True, baseCount=500, append=False, MultiIndex=True)
            log.info("Saved minimal mi_data: %s rows, cols: %s" % (len(df_mi_write), df_mi_write.columns.tolist()))
            log.info("hdf5 class all (trajectory) time:%0.2f" % (time.time() - time_s))
            
            # 2. 准备实时全量数据 -> sina_data.h5 (保存在 dd 中)
            dd = df.copy()
            log.info("Prepared sina_data: %s rows" % (len(dd)))
        
        if ('nlow' not in df.columns or 'nhigh' not in df.columns) and  ((cct.get_trade_date_status() and 924 < cct.get_now_time_int() <= 1501)  or  cct.get_now_time_int() > 1500 ):
            h5 = h5a.load_hdf_db(h5_fname, h5_table, timelimit=False)
            time_s = time.time()
            if cct.get_trade_date_status() and cct.get_now_time_int() <= 945:
                run_col = ['low', 'high', 'close']
                startime = '09:25:00'
                # endtime = '10:00:00'
                endtime = '09:35:00'
                dd = self.get_col_agg_df(h5, dd, run_col, all_func, startime, endtime)
                startime = '09:25:00'
                # endtime = '10:00:00'
                endtime = '09:35:00'
                run_col = {'close': 'std'}
                dd = self.get_col_agg_df(h5, dd, run_col, run_col, startime, endtime)
                dd.rename(columns={'std': 'nstd'}, inplace=True)
                if dd is not None and len(dd) > 0 and  'nclose' in dd.columns and 'nstd' in dd.columns:
                    for co in ['nclose','nstd']:
                        dd[co] = dd[co].apply(lambda x: round(x, 2))

            else:
                run_col = ['low','high']
                startime = '09:25:00'
                # endtime = '10:00:00'
                endtime = '09:35:00'
                dd = self.get_col_agg_df(h5, dd, run_col, all_func, startime, endtime)

                # run_col = ['high']
                # startime = '09:25:00'
                # endtime = '10:30:00'
                # dd = self.get_col_agg_df(h5, dd, run_col, all_func, startime, endtime)

                startime = '09:25:00'
                endtime = '15:01:00'
                run_col = ['close']
                # h5 = cct.get_limit_multiIndex_Group(h5, freq='15T', col=run_col,start=startime, end=endtime)
                # time_s=time.time()
                dd = self.get_col_agg_df(h5, dd, run_col, all_func, startime, endtime)
            log.info("agg_df_all_time:%0.2f" % (time.time() - time_s))

        h5a.write_hdf_db(self.hdf_name, dd, self.table, index=index)
        logtime = cct.get_config_value_ramfile(self.hdf_name,currvalue=time.time(),xtype='time',update=True)
        log.info("wr end:%0.2f" % (time.time() - self.start_t))
        dd = self.combine_lastbuy(dd)

        if dd is not None and len(dd) > 0 and  'nclose' in dd.columns and 'nstd' in dd.columns:
            for co in ['nclose','nstd']:
                dd[co] = dd[co].apply(lambda x: round(x, 2))
        if 'ticktime' in dd.columns:
            dd['ticktime'] = pd.to_datetime(dd['ticktime'])
            
        return dd

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
    import ipdb;ipdb.set_trace()
    
    print(len(df))
    print(f"df.loc['002786']: {df.loc['002786']}")
    print((df[-5:][['open','close']].T))

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
    code_agg = '601939'
    dd = sina.get_stock_code_data([code_agg,'600050','002350', '601899',\
      '603363','000868','603917','600392','300713','000933','002505','603676'])
    print((dd.T))

    print((dd.loc[:, ['name','open','low','high','close', 'ticktime']], dd.shape))
    # print((dd.loc[:, ['name','open','low','high','close', 'nclose', 'nlow', 'nhigh', 'nstd', 'ticktime']], dd.shape))

    sys.exit(0)
    
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
    
    if cct.get_trade_date_status() and cct.get_now_time_int() <= 1000:
        run_col = ['low', 'high', 'close']
        startime = None
        # endtime = '10:00:00'
        endtime = '09:35:00'
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
