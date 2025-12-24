# -*- coding:utf-8 -*-
import time
import gc
import pandas as pd
from typing import Any, Optional, Union, Dict, List
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct
from JohnsonUtil import LoggerFactory
from JSONData import tdx_data_Day as tdd
from JSONData import stockFilter as stf
from tdx_utils import clean_bad_columns, sanitize, clean_expired_tdx_file
from db_utils import get_indb_df

START_INIT = 0
PIPE_NAME = r"\\.\pipe\my_named_pipe"

def calc_compute_volume(top_all: pd.DataFrame, logger: Any, resample: str = 'd', virtual: bool = True) -> pd.Series:
    """计算成交量（虚拟量或原始量）"""
    ratio_t = cct.get_work_time_ratio(resample=resample)
    logger.info(f'ratio_t: {round(ratio_t, 2)}')

    if virtual:
        # 虚拟量 = volume / last6vol / ratio_t
        volumes = top_all['volume'] / top_all['last6vol'] / ratio_t
        return volumes.round(1)
    else:
        # 原始量 = 虚拟量 * last6vol * ratio_t
        volumes = top_all['volume'] * top_all['last6vol'] * ratio_t
        return volumes.round(1)

def calc_indicators(top_all: pd.DataFrame, logger: Any, resample: str) -> pd.DataFrame:
    """指标计算"""
    top_all['volume'] = calc_compute_volume(top_all, logger, resample=resample, virtual=True)

    now_time = cct.get_now_time_int()
    if cct.get_trade_date_status():
        logger.info(f'lastbuy :{"lastbuy" in top_all.columns}')
        if 'lastbuy' in top_all.columns:
            if 915 < now_time < 930:
                top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
            elif 926 < now_time < 1455:
                top_all['dff'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
            else:
                top_all['dff'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
        else:
            top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
            top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
    else:
        top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
        top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
        
    return top_all.sort_values(by=['dff','percent','volume','ratio','couts'], ascending=[0,0,0,1,1])

# def fetch_and_process_renewbug(shared_dict: Dict[str, Any], queue: Any, blkname: str = "boll", 
#                       flag: Any = None, log_level: Any = None, detect_calc_support_var: Any = None,
#                       marketInit: str = "all", marketblk: str = "boll",
#                       duration_sleep_time: int = 5, ramdisk_dir: str = cct.get_ramdisk_dir()) -> None:
#     """后台数据获取与处理进程"""
#     logger = LoggerFactory.getLogger()
#     if log_level is not None:
#         logger.setLevel(log_level.value)
#     logger.info(f"子进程开始，日志等级: {log_level.value if hasattr(log_level, 'value') else log_level}")
    
#     global START_INIT
#     g_values = cct.GlobalValues(shared_dict)
#     resample = g_values.getkey("resample") or "d"
#     market = g_values.getkey("market", marketInit)
#     blkname = g_values.getkey("blkname", marketblk)
#     logger.info(f"当前选择市场: {market}, blkname={blkname}")
#     st_key_sort = g_values.getkey("st_key_sort", "3 0")
    
#     lastpTDX_DF, top_all = pd.DataFrame(), pd.DataFrame()
#     detect_calc_support_val = detect_calc_support_var.value if hasattr(detect_calc_support_var, 'value') else False
#     logger.info(f"init resample: {resample} flag: {flag.value if flag else 'None'} detect_calc_support: {detect_calc_support_val}")
    
#     while True:
#         try:
#             time_s = time.time()
#             if flag is not None and not flag.value:
#                 for _ in range(5):
#                     if flag.value: break
#                     time.sleep(1)
#                 continue
            
#             # 检查配置更新
#             new_resample = g_values.getkey("resample") or "d"
#             if new_resample != resample:
#                 logger.info(f'resample changed: {resample} -> {new_resample}')
#                 resample = new_resample
#                 top_all = pd.DataFrame()
#                 lastpTDX_DF = pd.DataFrame()
            
#             new_market = g_values.getkey("market", marketInit)
#             if new_market != market:
#                 logger.info(f'market changed: {market} -> {new_market}')
#                 market = new_market
#                 top_all = pd.DataFrame()
#                 lastpTDX_DF = pd.DataFrame()
            
#             st_key_sort = g_values.getkey("st_key_sort", "3 0")
            
#             # 清理逻辑
#             if start_init > 0 and 830 <= cct.get_now_time_int() <= 915:
#                 today = cct.get_today()
#                 if not (g_values.getkey("tdx.init.done") is True and g_values.getkey("tdx.init.date") == today):
#                     if clean_expired_tdx_file(logger, g_values, cct.get_trade_date_status, cct.get_today, 
#                                             cct.get_now_time_int, cct.get_ramdisk_path, ramdisk_dir):
#                         now_time = cct.get_now_time_int()
#                         if now_time <= 915:
#                             time_init = time.time()
#                             start_init = 0
#                             top_now = tdd.getSinaAlldf(market=market, vol=ct.json_countVol, vtype=ct.json_countType)
#                             resamples = ['d', '3d', 'w', 'm'] if now_time <= 900 else ['3d']
#                             for res_m in resamples:
#                                 if res_m != resample:
#                                     tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days[res_m], resample=res_m)
#                             g_values.setkey("tdx.init.done", True)
#                             g_values.setkey("tdx.init.date", today)
#                             logger.info(f"init_tdx done, elapsed: {time.time() - time_init:.2f}s")
                        
#                         for _ in range(30):
#                             if flag and not flag.value: break
#                             time.sleep(1)
#                         continue

#             if start_init > 0 and (not cct.get_work_time()):
#                 for _ in range(5):
#                     if flag and not flag.value: break
#                     time.sleep(1)
#                 continue

#             # 获取数据
#             if market == 'indb':
#                 indf = get_indb_df()
#                 stock_code_list = indf.code.tolist()
#                 top_now = tdd.getSinaAlldf(market=stock_code_list, vol=ct.json_countVol, vtype=ct.json_countType)
#             else:
#                 top_now = tdd.getSinaAlldf(market=market, vol=ct.json_countVol, vtype=ct.json_countType)
                
#             if top_now.empty:
#                 time.sleep(duration_sleep_time)
#                 continue

#             # 合并与计算
#             detect_val = detect_calc_support_var.value if hasattr(detect_calc_support_var, 'value') else False
#             if top_all.empty:
#                 if lastpTDX_DF.empty:
#                     top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days[resample], 
#                                                                    resample=resample, detect_calc_support=detect_val)
#                 else:
#                     top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF, detect_calc_support=detect_val)
#             else:
#                 top_all = cct.combine_dataFrame(top_all, top_now, col="couts", compare="dff")

#             top_all = calc_indicators(top_all, logger, resample)
            
#             # 过滤与排序
#             sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort, top_all) if not top_all.empty else ct.get_market_sort_value_key(st_key_sort)
            
#             top_temp = top_all.copy()
#             top_temp = stf.getBollFilter(df=top_temp, resample=resample, down=False)
#             top_temp = top_temp.sort_values(by=sort_cols, ascending=sort_keys)
            
#             df_all = clean_bad_columns(top_temp)
#             df_all = sanitize(df_all)
#             queue.put(df_all)
#             gc.collect()
            
#             logger.info(f'now: {cct.get_now_time_int()} elapsed: {time.time() - time_s:.1f}s, count: {len(df_all)}, next sleep: {duration_sleep_time}')
#             for _ in range(duration_sleep_time):
#                 if flag and not flag.value: break
#                 time.sleep(0.5)
#             start_init = 1

#         except Exception as e:
#             logger.error(f"Error in background process: {e}", exc_info=True)
#             time.sleep(duration_sleep_time)

def send_code_via_pipe(code: Union[str, Dict[str, Any]], logger: Any,pipe_name: str=PIPE_NAME) -> bool:
    """通过命名管道发送股票代码"""
    import win32file
    if isinstance(code, dict):
        code = json.dumps(code, ensure_ascii=False)
    try:
        handle = win32file.CreateFile(
            pipe_name, win32file.GENERIC_WRITE, 0, None,
            win32file.OPEN_EXISTING, 0, None
        )
        win32file.WriteFile(handle, code.encode("utf-8"))
        win32file.CloseHandle(handle)
        return True
    except Exception as e:
        logger.info(f"发送数据到管道失败: {e}")
    return False

def fetch_and_process(shared_dict: Dict[str, Any], queue: Any, blkname: str = "boll", 
                      flag: Any = None, log_level: Any = None, detect_calc_support_var: Any = None,
                      marketInit: str = "all", marketblk: str = "boll",
                      duration_sleep_time: int = 120, ramdisk_dir: str = cct.get_ramdisk_dir()) -> None:
    """后台数据获取与处理进程"""
    logger = LoggerFactory.getLogger()
    if log_level is not None:
        logger.setLevel(log_level.value)
    logger.info(f"子进程开始，日志等级: {log_level.value if hasattr(log_level, 'value') else log_level} duration_sleep_time:{duration_sleep_time}")
    
    START_INIT = 0
    g_values = cct.GlobalValues(shared_dict)
    resample = g_values.getkey("resample") or "d"
    market = g_values.getkey("market", marketInit)
    blkname = g_values.getkey("blkname", marketblk)
    st_key_sort = g_values.getkey("st_key_sort", "3 0")
    logger.info(f"当前选择市场: {market}, blkname={blkname} st_key_sort:{st_key_sort}")
    
    lastpTDX_DF, top_all = pd.DataFrame(), pd.DataFrame()
    detect_calc_support_val = detect_calc_support_var.value if hasattr(detect_calc_support_var, 'value') else False
    logger.info(f"init resample: {resample} flag: {flag.value if flag else 'None'} detect_calc_support: {detect_calc_support_val}")
    
    while True:
        try:
            time_s = time.time()
            if not flag.value:   # 停止刷新
                   for _ in range(5):
                        if not flag.value: break
                        time.sleep(1)
                   # logger.info(f'flag.value : {flag.value} 停止更新')
                   continue
            elif g_values.getkey("resample") and  g_values.getkey("resample") !=  resample:
                top_now = pd.DataFrame()
                top_all = pd.DataFrame()
                lastpTDX_DF = pd.DataFrame()
                logger.info(f'resample : new resample : {g_values.getkey("resample")} last resample : {resample} top_now:{len(top_now)} top_all:{len(top_all)} lastpTDX_DF:{len(lastpTDX_DF)}')
            elif g_values.getkey("market") and  g_values.getkey("market") !=  market:
                # logger.info(f'market : new : {g_values.getkey("market")} last : {market} ')
                top_now = pd.DataFrame()
                top_all = pd.DataFrame()
                lastpTDX_DF = pd.DataFrame()
                logger.info(f'market : new resample: {g_values.getkey("market")} last resample: {resample} top_now:{len(top_now)} top_all:{len(top_all)} lastpTDX_DF:{len(lastpTDX_DF)}')
            elif g_values.getkey("st_key_sort") and  g_values.getkey("st_key_sort") !=  st_key_sort:
                # logger.info(f'st_key_sort : new : {g_values.getkey("st_key_sort")} last : {st_key_sort} ')
                st_key_sort = g_values.getkey("st_key_sort")
            elif START_INIT > 0 and 830 <= cct.get_now_time_int() <= 915:
                today = cct.get_today()
                # 0️⃣ init 今天已经完成 → 直接跳过
                if (
                    g_values.getkey("tdx.init.done") is True
                    and g_values.getkey("tdx.init.date") == today
                ):
                    continue

                # 1️⃣ 清理（未完成 → 不允许 init）
                # if not clean_expired_tdx_file(logger, g_values):
                if not clean_expired_tdx_file(logger, g_values, cct.get_trade_date_status, cct.get_today, cct.get_now_time_int, cct.get_ramdisk_path, ramdisk_dir):
                    logger.info(f"{today} 清理尚未完成，跳过 init_tdx")
                    # 5️⃣ 节流
                    for _ in range(30):
                        if not flag.value:
                            break
                        time.sleep(1)
                    continue

                # 2️⃣ 再次确认时间（防止跨 09:15）
                now_time = cct.get_now_time_int()
                if now_time > 915:
                    logger.info(
                        f"{today} 已超过初始化截止时间 {now_time}"
                    )
                    continue

                # 3️⃣ 正式 init（只会执行一次）
                time_init = time.time()
                START_INIT = 0

                top_now = tdd.getSinaAlldf(
                    market=market,
                    vol=ct.json_countVol,
                    vtype=ct.json_countType
                )

                if now_time <= 900:
                    resamples = ['d','3d', 'w', 'm']
                else:
                    resamples = ['3d']

                for res_m in resamples:
                    time_init_m = time.time()
                    if res_m != g_values.getkey("resample"):
                        now_time = cct.get_now_time_int()
                        if now_time <= 905:
                            logger.info(f"start init_tdx resample: {res_m}")
                            tdd.get_append_lastp_to_df(
                                top_now,
                                dl=ct.Resample_LABELS_Days[res_m],
                                resample=res_m)
                        else:
                            logger.info(f'resample:{res_m} now_time:{now_time} > 905 终止初始化 init_tdx 用时:{time.time()-time_init_m:.2f}')
                            break
                        logger.info(f'resample:{res_m} init_tdx 用时:{time.time()-time_init_m:.2f}')
                
                # 4️⃣ 关键：标记 init 已完成（跨循环）
                g_values.setkey("tdx.init.done", True)
                g_values.setkey("tdx.init.date", today)
                top_all = pd.DataFrame()
                lastpTDX_DF = pd.DataFrame()
                logger.info(
                    f"init_tdx 总用时: {time.time() - time_init:.2f}s tdx.init.done:{g_values.getkey('tdx.init.done')} tdx.init.date:{g_values.getkey('tdx.init.date')} "
                )

                # 5️⃣ 节流
                for _ in range(duration_sleep_time):
                    if not flag.value:
                        break
                    time.sleep(1)
                continue

            elif START_INIT > 0 and (not cct.get_work_time()):
                    # logger.info(f'not worktime and work_duration')
                    for _ in range(5):
                        if not flag.value: break
                        time.sleep(1)
                    continue
            else:
                logger.info(f'start work : {cct.get_now_time()} get_work_time: {cct.get_work_time()} , START_INIT :{START_INIT} ')

            resample = g_values.getkey("resample") or "d"
            market = g_values.getkey("market", marketInit)        # all / sh / cyb / kcb / bj
            blkname = g_values.getkey("blkname", marketblk)  # 对应的 blk 文件
            st_key_sort = g_values.getkey("st_key_sort", st_key_sort)  # 对应的 blk 文件
            logger.info(f"resample Main  market : {market} resample: {resample} flag.value : {flag.value} blkname :{blkname} st_key_sort:{st_key_sort}")

            if market == 'indb':
                indf = get_indb_df()
                stock_code_list = indf.code.tolist()
                top_now = tdd.getSinaAlldf(market=stock_code_list,vol=ct.json_countVol, vtype=ct.json_countType)
            else:
                top_now = tdd.getSinaAlldf(market=market,vol=ct.json_countVol, vtype=ct.json_countType)
            if top_now.empty:
                logger.info("top_now.empty no data fetched")
                time.sleep(duration_sleep_time)
                continue
            logger.info(f"resample Main  top_now:{len(top_now)} market : {market}  {resample} flag.value : {flag.value} blkname :{blkname} st_key_sort:{st_key_sort}")
            # 合并与计算
            detect_val = detect_calc_support_var.value if hasattr(detect_calc_support_var, 'value') else False
            if top_all.empty:
                if lastpTDX_DF.empty:
                    top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days[resample], 
                                                                   resample=resample, detect_calc_support=detect_val)
                else:
                    top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF, detect_calc_support=detect_val)
            else:
                top_all = cct.combine_dataFrame(top_all, top_now, col="couts", compare="dff")

            top_all = calc_indicators(top_all, logger, resample)
            logger.info(f"resample Main  top_all:{len(top_all)} market : {market}  {resample} flag.value : {flag.value} blkname :{blkname} st_key_sort:{st_key_sort}")

            # top_all = calc_indicators(top_all, resample)

            if top_all is not None and not top_all.empty:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort,top_all)
            else:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort)

            logger.info(f'sort_cols : {sort_cols[:3]} sort_keys : {sort_keys[:3]}  st_key_sort : {st_key_sort[:3]}')
            top_temp = top_all.copy()
            top_temp=stf.getBollFilter(df=top_temp, resample=resample, down=False)
            top_temp = top_temp.sort_values(by=sort_cols, ascending=sort_keys)
            logger.info(f'resample: {resample} top_temp :  {top_temp.loc[:,["name"] + sort_cols[:7]][:10]} shape : {top_temp.shape} detect_calc_support:{detect_val}')
            df_all = clean_bad_columns(top_temp)
            df_all = sanitize(df_all)
            queue.put(df_all)
            gc.collect()
            logger.info(f'process now: {cct.get_now_time_int()} resample Main:{len(df_all)} sleep_time:{duration_sleep_time}  用时: {round(time.time() - time_s,1)/(len(df_all)+1):.2f} elapsed time: {round(time.time() - time_s,1)}s  START_INIT : {cct.get_now_time()} {START_INIT} fetch_and_process sleep:{duration_sleep_time} resample:{resample}')
            if cct.get_now_time_int() < 945:
                sleep_step = 0.5
            else:
                sleep_step = 1
            # cout_time = 0
            for _ in range(duration_sleep_time):
                if not flag.value:
                    break
                elif g_values.getkey("resample") and  g_values.getkey("resample") !=  resample:
                    break
                elif g_values.getkey("market") and  g_values.getkey("market") !=  market:
                    # logger.info(f'market : new : {g_values.getkey("market")} last : {market} ')
                    break
                elif g_values.getkey("st_key_sort") and  g_values.getkey("st_key_sort") !=  st_key_sort:
                    break
                time.sleep(sleep_step)
                # cout_time +=sleep_step
                # logger.info(f'cout_time:{cout_time} duration_sleep_time:{duration_sleep_time} sleep_step:{sleep_step}')
            START_INIT = 1

        except Exception as e:
            logger.error(f"resample: {resample} Error in background process: {e}", exc_info=True)
            time.sleep(duration_sleep_time)