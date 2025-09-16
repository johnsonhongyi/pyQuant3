import os
import time
import random
import subprocess
import logging
import platform
from pandas import HDFStore

log = logging.getLogger(__name__)

class SafeHDFStore(HDFStore):
    def __init__(self, fname, *args, **kwargs):
        """
        精简版 SafeHDFStore
        - 自动加锁，避免并发写入冲突
        - 支持压缩参数 (zlib, complevel=9)
        - 超过阈值大小时自动 ptrepack 压缩整理
        """
        # 可调参数
        self.probe_interval = kwargs.pop("probe_interval", 2)
        self.complevel = kwargs.pop("complevel", 9)
        self.complib = kwargs.pop("complib", "zlib")
        self.big_H5_Size_limit = kwargs.pop("size_limit", 500)  # MB
        self.config_ini = kwargs.pop("config_ini", None)  # 这里不用了，可以忽略

        # 文件路径
        self.fname = os.path.abspath(fname)
        self.fname_o = os.path.basename(fname)
        self.basedir = os.path.dirname(self.fname)
        self.temp_file = self.fname + "_tmp"

        # 锁文件
        self._lock = self.fname + ".lock"
        self.countlock = 0
        self.write_status = True
        self.h5_size_org = os.path.getsize(self.fname) / 1e6 if os.path.exists(self.fname) else 0

        # ptrepack 命令
        self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel={level} --complib={lib} {src} {dst}"

        # 获取写锁
        self.run(self.fname, *args, **kwargs)

    def run(self, fname, *args, **kwargs):
        while True:
            try:
                self._flock = os.open(self._lock, os.O_CREAT | os.O_EXCL)
                log.info("SafeHDF: %s lock acquired" % self._lock)
                break
            except (OSError, IOError) as e:
                if self.countlock <= 8:
                    time.sleep(round(random.randint(3, 10) / 1.2, 2))
                    self.countlock += 1
                else:
                    if os.path.exists(self._lock):
                        os.remove(self._lock)
                    log.warning("Force removed stale lock: %s" % self._lock)
            finally:
                pass

        # 调用 HDFStore 构造
        super().__init__(fname, *args, **kwargs)

    def __enter__(self):
        if self.write_status:
            return self

    def __exit__(self, *args, **kwargs):
        if self.write_status:
            super().__exit__(*args, **kwargs)
            os.close(self._flock)

            # 检查文件大小
            h5_size = os.path.getsize(self.fname) / 1e6
            new_limit = ((h5_size // self.big_H5_Size_limit) + 1) * self.big_H5_Size_limit
            log.info("fname:%s h5_size:%.2fMB limit:%dMB" % (self.fname, h5_size, self.big_H5_Size_limit))

            if h5_size > self.big_H5_Size_limit:
                log.info("Triggering ptrepack for %s" % self.fname)
                self._do_repack()

            if os.path.exists(self._lock):
                os.remove(self._lock)

    def _do_repack(self):
        """执行 ptrepack 压缩"""
        if os.path.exists(self.fname):
            if os.path.exists(self.temp_file):
                os.remove(self.temp_file)
            os.rename(self.fname, self.temp_file)

            cmd = self.ptrepack_cmds.format(
                level=self.complevel, lib=self.complib,
                src=self.temp_file, dst=self.fname
            )

            log.info("Running: %s" % cmd)
            p = subprocess.Popen(cmd, shell=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            p.wait()
            if p.returncode != 0:
                log.error("ptrepack error: %s" % p.communicate())
            else:
                if os.path.exists(self.temp_file):
                    os.remove(self.temp_file)

def load_hdf_db1(
    fname,
    table="all",
    code_l=None,
    timelimit=True,
    index=False,
    limit_time=300,       # 默认 300 秒
    dratio_limit=0.5,     # 默认允许最多 50% 缺失
    MultiIndex=False,
    showtable=False,):
    """
    精简版 HDF5 读取函数

    Parameters
    ----------
    fname : str
        HDF5 文件路径
    table : str
        读取的表 key
    code_l : list[str], optional
        需要过滤的代码列表
    timelimit : bool
        是否限制时间有效性
    index : bool
        是否转换 index
    limit_time : float
        timel 平均时间阈值 (秒)
    dratio_limit : float
        缺失比例限制
    MultiIndex : bool
        是否为多层索引
    showtable : bool
        是否显示所有 keys

    Returns
    -------
    pd.DataFrame or None
    """

    t0 = time.time()
    df, dd = None, None

    if not os.path.exists(fname):
        log.error("HDF5 file not found: %s", fname)
        return None

    # 读取表
    with SafeHDFStore(fname, mode="r") as store:
        if store is None:
            return None
        keys = list(store.keys())
        if showtable:
            print(f"fname: {fname}, keys: {keys}")

        if "/" + table not in keys:
            log.error("%s not found in %s", table, fname)
            return None

        dd = store[table]

    if dd is None or len(dd) == 0:
        log.warning("Empty table %s in %s", table, fname)
        return None

    # --- 按 code_l 过滤 ---
    if code_l is not None:
        if not MultiIndex:
            if index:
                code_l = [str(1000000 - int(x)) if x.startswith("0") else x for x in code_l]
            dif_co = list(set(dd.index) & set(code_l))

            if len(code_l) > 0:
                dratio = (len(code_l) - len(dif_co)) / float(len(code_l))
            else:
                dratio = 0.0

            log.info("find all:%s missing:%s dratio:%.2f",
                     len(code_l), len(code_l) - len(dif_co), dratio)

            # 时间限制
            if timelimit and "timel" in dd.columns:
                dd = dd.loc[dif_co]
                o_time = [time.time() - t for t in dd[dd.timel != 0].timel.tolist()]
                if len(o_time) > 0:
                    l_time = np.mean(o_time)

                    return_hdf_status = l_time < limit_time
                    log.info("return_hdf_status:%s mean_time:%.2f limit:%.2f",
                             return_hdf_status, l_time, limit_time)
                    if return_hdf_status:
                        df = dd
            else:
                df = dd.loc[dif_co]

            if dratio > dratio_limit:
                log.warning("Too many codes missing: %.2f > %.2f",
                            dratio, dratio_limit)
                return None
        else:
            # 多层索引
            df = dd.loc[dd.index.isin(code_l, level="code")]
    else:
        df = dd

    # --- 统一清理 ---
    if df is not None and len(df) > 0:
        df = df.fillna(0)
        df = df[~df.index.duplicated(keep="last")]

        # MultiIndex 去重逻辑
        if MultiIndex and "volume" in df.columns:
            count_before = len(df)
            df = df.drop_duplicates()
            dratio = len(df) / float(count_before)
            log.debug("MultiIndex drop_duplicates: before=%d after=%d ratio=%.2f",
                      count_before, len(df), dratio)

    log.info("load_hdf_time: %.2f sec", time.time() - t0)
    return df

import pandas as pd
import time, os, numpy as np

def load_hdf_db_code_col(
    fname,
    table="all",
    code=None,             # 单个 code
    code_l=None,           # 多个 code 列表
    timelimit=True,
    index=False,
    limit_time=300,        # timel 平均时间阈值 (秒)
    dratio_limit=0.5,      # 缺失比例限制
    MultiIndex=False,
    showtable=False,
):
    """
    精简版 HDF5 读取函数，支持按 code 查询

    Parameters
    ----------
    fname : str
        HDF5 文件路径
    table : str
        读取的表 key
    code : str, optional
        单个股票代码，直接条件查询
    code_l : list[str], optional
        需要过滤的代码列表
    timelimit : bool
        是否限制时间有效性
    index : bool
        是否转换 index
    limit_time : float
        timel 平均时间阈值 (秒)
    dratio_limit : float
        缺失比例限制
    MultiIndex : bool
        是否为多层索引
    showtable : bool
        是否显示所有 keys

    Returns
    -------
    pd.DataFrame or None
    """

    t0 = time.time()
    df, dd = None, None

    if not os.path.exists(fname):
        log.error("HDF5 file not found: %s", fname)
        return None

    with SafeHDFStore(fname, mode="r") as store:
        if store is None:
            return None
        keys = list(store.keys())
        if showtable:
            print(f"fname: {fname}, keys: {keys}")

        if "/" + table not in keys:
            log.error("%s not found in %s", table, fname)
            return None

        # --- 优化: 直接按 code 查询 ---
        if code is not None:
            try:
                dd = store.select(table, where=f'code="{code}"')
            except Exception as e:
                log.error("select code %s failed: %s", code, e)
                return None
        elif code_l is not None and len(code_l) > 0:
            try:
                dd = store.select(table, where=[f'code in {code_l}'])
            except Exception as e:
                log.error("select code_l failed: %s", e)
                return None
        else:
            dd = store[table]

    if dd is None or len(dd) == 0:
        log.warning("Empty result from %s in %s", table, fname)
        return None

    # --- 时间过滤 ---
    if timelimit and "timel" in dd.columns:
        o_time = [time.time() - t for t in dd[dd.timel != 0].timel.tolist()]
        if len(o_time) > 0:
            l_time = np.mean(o_time)
            return_hdf_status = l_time < limit_time
            log.info("return_hdf_status:%s mean_time:%.2f limit:%.2f",
                     return_hdf_status, l_time, limit_time)
            if not return_hdf_status:
                return None

    df = dd

    # --- 统一清理 ---
    if df is not None and len(df) > 0:
        df = df.fillna(0)
        df = df[~df.index.duplicated(keep="last")]

        if MultiIndex and "volume" in df.columns:
            count_before = len(df)
            df = df.drop_duplicates()
            dratio = len(df) / float(count_before)
            log.debug("MultiIndex drop_duplicates: before=%d after=%d ratio=%.2f",
                      count_before, len(df), dratio)

    log.info("load_hdf_time: %.2f sec", time.time() - t0)
    return df

def write_hdf_with_code(fname, table, df, index=True, complib='zlib', complevel=9):
    """
    写入 HDF5 并把 code 加入 data_columns
    """
    if df is None or len(df) == 0:
        print("Empty DataFrame, skip write")
        return

    # 如果是 MultiIndex，确保 code 是列
    if isinstance(df.index, pd.MultiIndex) and 'code' in df.index.names:
        df_reset = df.reset_index(level='code')
    elif 'code' not in df.columns:
        # 单索引，假设 index 是 code
        df_reset = df.copy()
        df_reset['code'] = df_reset.index
    else:
        df_reset = df.copy()

    # 确保 code 在 data_columns
    df_reset.to_hdf(
        fname,
        key=table,
        mode='a',
        format='table',          # table 格式才能用 data_columns
        data_columns=['code'],   # 指定 code 可筛选
        complevel=complevel,
        complib=complib,
        index=index
    )
    print(f"Wrote table {table} to {fname}, rows: {len(df_reset)}")

def write_hdf_db_optimized(
    fname,
    df,
    table='all',
    index=False,
    complib='blosc',
    append=True,
    MultiIndex=False,
    rewrite=False,
    showtable=False,
    data_columns=['code']
):
    """
    HDF5 写入函数优化版，默认 data_columns=['code']

    支持：
    - MultiIndex / 普通索引
    - 自动去重、填充
    - rewrite / append 模式
    """
    import pandas as pd, time, os

    if df is None or df.empty:
        return False

    # 处理 index
    if not MultiIndex and 'code' in df.columns:
        df = df.set_index('code')

    # 去重 / 填充
    df = df.fillna(0)
    df = df[~df.index.duplicated(keep='last')]

    # 内存优化
    df = cct.reduce_memory_usage(df, verbose=False)

    with SafeHDFStore(fname) as h5:
        if h5 is None:
            log.error("HDFStore open failed: %s" % fname)
            return False

        if rewrite and '/' + table in h5.keys():
            h5.remove(table)

        kwargs = dict(
            format='table',
            append=append,
            complib=complib,
            data_columns=data_columns,
            index=not MultiIndex
        )

        h5.put(table, df, **kwargs)
        h5.flush()
        if showtable:
            print(f"HDF5 write done: {fname}, keys: {h5.keys()}")

    return True


def load_hdf_db_optimized(
    fname,
    table='all',
    code_l=None,
    columns=None,
    timelimit=False,
    index=False,
    MultiIndex=False,
    showtable=False
):
    """
    HDF5 读取优化版

    支持：
    - code_l 筛选（利用 data_columns=['code']）
    - columns 列选择
    - MultiIndex / 普通索引
    - 保持兼容旧表（无 data_columns）
    """
    import pandas as pd, time, os

    df = None

    if not os.path.exists(fname):
        log.error("HDF5 file not found: %s" % fname)
        return None

    with SafeHDFStore(fname, mode='r') as store:
        if store is None:
            return None
        keys = store.keys()
        if showtable:
            print(f"keys: {keys}")
        if '/' + table not in keys:
            log.error("table %s not found in %s" % (table, fname))
            return None

        storer = store.get_storer(table)

        # 判断表是否有 code 列
        has_code_column = 'code' in (storer.data_columns or [])

        # code_l 选择
        if code_l is not None and has_code_column:
            df = store.select(table, where=pd.Index(code_l, name='code'))
        else:
            df = store[table]

        # 列选择
        if columns is not None:
            df = df[columns]

    # 填充 / 去重
    if df is not None and not df.empty:
        df = df.fillna(0)
        df = df[~df.index.duplicated(keep='last')]

    return cct.reduce_memory_usage(df)


if __name__ == '__main__':
    # with SafeHDFStore("G:\\sina_data.h5") as store:
    #     store.load_hdf_db()
    # df2 = store["df"]


    # 全局开启 debug 日志
    # logging.basicConfig(
    #     level=logging.DEBUG,  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    #     format='%(asctime)s [%(levelname)s] %(message)s',
    #     datefmt='%Y-%m-%d %H:%M:%S'
    # )
    # log = logging.getLogger()  # 使用全局 logger



    # fname="G:\\sina_data.h5"
    # # store = SafeHDFStore(filename)
    # h5_fname = 'sina_MultiIndex_data'
    # h5_table = 'all' + '_' + str(30)
    
    time_s = time.time()
    sina_fname="G:\\sina_data.h5"
    sina_table='all' 

    # # h5 = load_hdf_db(sina_fname, table=sina_table, code_l=None, timelimit=False, dratio_limit=0.12)
    # h5 = load_hdf_db(sina_fname, table=sina_table,code='000002')
    h5 = load_hdf_db1(sina_fname, table=sina_table)
    h5 = load_hdf_db_optimized(sina_fname, table=sina_table)
    print(f'sina_fname time:{time.time() - time_s}')
    print(f'h5:{h5[:3]}')

    # # sina_MultiIndex_fname="G:\\sina_MultiIndex_data.h5"
    # sina_MultiIndex_fname="G:\\sina_MultiIndex_data_columns.h5"
    # # # store = SafeHDFStore(filename)
    # sina_MultiIndex_table = 'all' + '_' + str(30)
    # time_s = time.time()
    # # # h5_realTime = load_hdf_db(sina_MultiIndex_fname, table=sina_MultiIndex_table, code_l=None, timelimit=False, dratio_limit=0.12)
    # h5_realTime = load_hdf_db(sina_MultiIndex_fname, table=sina_MultiIndex_table,code_l=['000002','002739','600699'])
    # print(f'sina_MultiIndex_fname time:{time.time() - time_s}')
    # print(f'h5_realTime:{h5_realTime}')
    # import ipdb;ipdb.set_trace()

    # # print(f'sina_MultiIndex_fname:{h5_realTime[:10]}')
    # # import ipdb;ipdb.set_trace()



    # --- 示例 ---
    basedir = os.path.join("G:",os.sep )
    # fname = os.path.join(basedir, "sina_MultiIndex_data.h5")
    fname = os.path.join(basedir, "sina_data.h5")
    # table = 'all_30'
    table = 'all'


    # 读取数据
    df = load_hdf_db(fname, table=table, MultiIndex=False)
    import ipdb;ipdb.set_trace()

    # fname_data_col = os.path.join(basedir, "sina_MultiIndex_data_columns.h5") 
    fname_data_col = os.path.join(basedir, "sina_data_columns.h5") 
    # 写入 HDF5，带 code data_column
    write_hdf_with_code(fname_data_col, table, df)