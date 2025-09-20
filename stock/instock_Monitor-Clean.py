# -*- coding:utf-8 -*-
# !/usr/bin/env python
import gc
import re
import sys
import time
import pandas as pd

from docopt import docopt
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import LoggerFactory, commonTips as cct
import singleAnalyseUtil as sl
from JSONData import stockFilter as stf
from JSONData import tdx_data_Day as tdd


def init_logger(args):
    log = LoggerFactory.log
    if args['-d'] == 'debug':
        log_level = LoggerFactory.DEBUG
    elif args['-d'] == 'info':
        log_level = LoggerFactory.INFO
    else:
        log_level = LoggerFactory.ERROR
    log.setLevel(log_level)
    return log


def init_console():
    width, height = 163, 22
    cct.set_console(width, height)
    return width, height


def fetch_market_data(market_blk="bj"):
    return tdd.getSinaAlldf(
        market=market_blk, vol=ct.json_countVol, vtype=ct.json_countType
    )


def init_or_update_top_all(top_now, lastpTDX_DF, duration_date, resample):
    """初始化或更新 top_all"""
    if top_now.empty:
        return pd.DataFrame(), lastpTDX_DF
    if lastpTDX_DF.empty:
        top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(
            top_now, dl=duration_date, resample=resample
        )
    else:
        top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF)
    return top_all, lastpTDX_DF


def calc_indicators(top_all, resample):
    """计算 boll, df2, dff 等指标"""
    if cct.get_trade_date_status() == 'True':
        for co in ['boll', 'df2']:
            top_all[co] = list(
                map(
                    lambda x, y, m, z: z + (1 if (x > y) else 0),
                    top_all.close.values,
                    top_all.upper.values,
                    top_all.llastp.values,
                    top_all[co].values,
                )
            )
    # 过滤
    top_all = top_all[(top_all.df2 > 0) & (top_all.boll > 0)]

    # 量能调整
    ratio_t = cct.get_work_time_ratio(resample=resample)
    top_all['volume'] = list(
        map(
            lambda x, y: round(x / y / ratio_t, 1),
            top_all['volume'].values,
            top_all.last6vol.values,
        )
    )

    # dff 相关
    now_time = cct.get_now_time_int()
    if 'lastbuy' in top_all.columns:
        if 915 < now_time < 930:
            top_all['dff'] = (
                (top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100
            ).round(1)
            top_all['dff2'] = (
                (top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100
            ).round(1)
        elif 926 < now_time < 1455:
            top_all['dff'] = (
                (top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100
            ).round(1)
            top_all['dff2'] = (
                (top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100
            ).round(1)
        else:
            top_all['dff'] = (
                (top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100
            ).round(1)
            top_all['dff2'] = (
                (top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100
            ).round(1)
    else:
        top_all['dff'] = (
            (top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100
        ).round(1)

    return top_all.sort_values(
        by=['dff', 'percent', 'volume', 'ratio', 'couts'],
        ascending=[0, 0, 0, 1, 1],
    )


def filter_top_temp(top_all, st_key_sort, duration_date, blkname, resample):
    """
    根据不同 blkname 对 top_all 进行过滤
    - init: 使用 initfilter
    - init_false: 使用 initfilter_false
    - search: 搜索关键字
    - boll: 进行布林带筛选（增加 None/NaN 保护）
    - nhigh: 新高过滤
    - nlow: 新低过滤
    """

    top_temp = top_all.copy()

    if blkname == "init":
        top_temp = stf.initfilter(top_temp, st_key_sort, duration_date)

    elif blkname == "init_false":
        top_temp = stf.initfilter_false(top_temp, st_key_sort, duration_date)

    elif blkname == "search":
        top_temp = stf.searchDf(top_temp, search_key)

    elif blkname == "boll":
        # 🚨 修复：补回原始版里的空值保护
        if "market_value" in top_temp.columns:
            top_temp = top_temp.dropna(subset=["market_value"])
            top_temp["market_value"] = top_temp["market_value"].fillna("0")

        top_temp = stf.getBollFilter(df=top_temp, resample=resample, down=True)

    elif blkname == "nhigh":
        top_temp = stf.getnewhigh_or_low(top_temp, newhigh=True)

    elif blkname == "nlow":
        top_temp = stf.getnewhigh_or_low(top_temp, newhigh=False)

    return top_temp


def print_market_info(top_all, top_temp, du_date, blkname, resample, width, height):
    """打印行情表格和统计"""
    goldstock = len(
        top_all[
            (top_all.buy >= top_all.lhigh * 0.99)
            & (top_all.buy >= top_all.llastp * 0.99)
        ]
    )
    nhigh = top_temp[top_temp.close > top_temp.nhigh] if "nhigh" in top_temp.columns else []
    nlow = top_temp[top_temp.close > top_temp.nlow] if "nlow" in top_temp.columns else []

    print(
        "G:%s Rt:%0.1f dT:%s N:%s T:%s nh:%s nlow:%s"
        % (
            goldstock,
            float(time.time()),
            cct.get_time_to_date(time.time()),
            cct.get_now_time(),
            len(top_temp),
            len(nhigh),
            len(nlow),
        )
    )

    # 排序
    market_sort_value, market_sort_value_key = ct.get_market_sort_value_key("1")
    top_temp = top_temp.sort_values(by=market_sort_value, ascending=market_sort_value_key)

    # 输出表格
    ct_MonitorMarket_Values = ct.get_Duration_format_Values(
        ct.Monitor_format_trade, market_sort_value[:2]
    )
    top_dd=cct.combine_dataFrame(
        top_temp.loc[:, ct_MonitorMarket_Values][:10], top_temp.loc[:, ct_MonitorMarket_Values][:5], append=True, clean=True)
    table, widths=cct.format_for_print(
        top_dd.loc[[col for col in top_dd[:10].index if col in top_temp[:10].index]], widths=True)
    # table, widths = cct.format_for_print(top_temp.head(10), widths=True)

    cct.set_console(
        width, height, title=[du_date, f"G:{len(top_all)}", f"zxg: {blkname} resample:{resample}"]
    )
    print(table)
    # print_market_info_df(top_temp.head(10), top_temp[-4:])
    cct.counterCategory(top_temp)

def print_market_info_df(top_dd, top_temp):
    """
    打印市场信息，替代 PrettyTable
    """
    print("\n>>> Top 10 (交集部分):")
    common_index = top_dd[:10].index.intersection(top_temp[:10].index)
    if not common_index.empty:
        print(top_dd.loc[common_index])
    else:
        print("无交集数据")

    print("\n>>> Category Counter:")
    if "category" in top_temp.columns:
        print(top_temp["category"].value_counts(dropna=False))
    else:
        print("无 category 列")

    print("\n>>> Last 4:")
    print(top_dd.tail(4))

def main():
    args = docopt(cct.sina_doc, version="SinaMarket")
    log = init_logger(args)
    width, height = init_console()

    duration_date = ct.duration_date_day
    resample = "d"
    blkname = "063.blk"
    block_path = tdd.get_tdx_dir_blocknew() + blkname
    lastpTDX_DF, top_all = pd.DataFrame(), pd.DataFrame()

    while True:
        try:
            top_now = fetch_market_data()
            if top_now.empty:
                print("no data")
                continue

            if top_all.empty:
                top_all, lastpTDX_DF = init_or_update_top_all(
                    top_now, lastpTDX_DF, duration_date, resample
                )
            else:
                top_all = cct.combine_dataFrame(top_all, top_now, col="couts", compare="dff")

            top_all = calc_indicators(top_all, resample)
            top_temp = filter_top_temp(top_all, "1", duration_date, blkname, resample)
            print_market_info(top_all, top_temp, duration_date, blkname, resample, width, height)

            gc.collect()
            cct.sleep(ct.duration_sleep_time)

        except KeyboardInterrupt:
            print("\n>>> Enter command (q=exit, s=search, r=resample, b=blkname):")
            st = input("> ").strip()
            
            if st.lower() in ["q", "exit", "e"]:
                print("Exiting...")
                sys.exit(0)
            elif st.startswith("s "):  # 搜索关键字
                search_key = st[2:].strip()
                cct.GlobalValues().setkey("search_key", search_key)
                print(f"Search key set: {search_key}")
            elif st.startswith("r "):  # 改变 resample
                new_resample = st[2:].strip()
                cct.GlobalValues().setkey("resample", new_resample)
                print(f"Resample set: {new_resample}")
            elif st.startswith("b "):  # 改变 blkname
                blkname = st[2:].strip()
                print(f"Block/Filter set: {blkname}")
            else:
                print("Unknown command")
        except Exception as e:
            import traceback

            print("Error:", e)
            traceback.print_exc()
            cct.sleeprandom(ct.duration_sleep_time / 2)


if __name__ == "__main__":
    main()
