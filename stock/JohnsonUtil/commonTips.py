# -*- encoding: utf-8 -*-

import argparse
import datetime
import os
import platform
import re
import sys
sys.path.append("..")
import time
import random
# from compiler.ast import flatten  #py2
import collections.abc              #py3

from multiprocessing.pool import ThreadPool
from multiprocessing import cpu_count

import pandas as pd
# import trollius as asyncio
# from trollius.coroutines import From
import asyncio
import argparse


from JohnsonUtil import LoggerFactory
from JohnsonUtil.prettytable import PrettyTable
from JohnsonUtil import johnson_cons as ct
# from JohnsonUtil import inStockDb as inDb

import traceback
import socket
from configobj import ConfigObj
import importlib
log = LoggerFactory.log
from tqdm import tqdm
# import win32MoveCom
# log.setLevel(Log.DEBUG)
# import numba as nb
import numpy as np
import subprocess
import a_trade_calendar
# from py_mini_racer import py_mini_racer
from textwrap import fill
from JohnsonUtil.prettytable import ALL as ALL

try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib.request import urlopen, Request

import urllib.error
import requests
requests.adapters.DEFAULT_RETRIES = 0
# sys.path.append("..")
# sys.path.append("..")
# print sys.path
# from JSONData import tdx_data_Day as tdd
global initGlobalValue
global last_trade_date,is_trade_date_today


initGlobalValue = 0
# clean_terminal = ["Python Launcher", 'Johnson — -bash', 'Johnson — python']
clean_terminal = ["Python Launcher", 'Johnson — -bash', 'Johnson — python']
writecode = "cct.write_to_blocknew(block_path, dd.index.tolist())"
perdall = "df[df.columns[(df.columns >= 'per1d') & (df.columns <= 'per%sd'%(ct.compute_lastdays))]][:1]"
perdallc = "df[df.columns[(df.columns >= 'perc1d') & (df.columns <= 'perc%sd'%(ct.compute_lastdays))]][:1]"
perdalla = "df[df.columns[ ((df.columns >= 'per1d') & (df.columns <= 'per%sd'%(ct.compute_lastdays))) | ((df.columns >= 'du1d') & (df.columns <= 'du%sd'%(ct.compute_lastdays)))]][:1]"
perdallu = "df[df.columns[ ((df.columns >= 'du1d') & (df.columns <= 'du%sd'%(ct.compute_lastdays)))]][:1]"
root_path=['D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\','/Users/Johnson/Documents/Quant/pyQuant3/stock']
dfcf_path = 'D:\\MacTools\\WinTools\\eastmoney\\swc8\\config\\User\\6327113578970854\\StockwayStock.ini'

win10Lengend = r'D:\Quant\new_tdx2'
# win10Lengend = r'D:\Program\gfzq'
win10Lixin = r'C:\zd_zszq'
win10Triton = r'D:\MacTools\WinTools\new_tdx2'
#东兴
win10pazq = r'D:\MacTools\WinTools\new_tdx2'
win10dxzq = r'D:\MacTools\WinTools\zd_dxzq'

win7rootAsus = r'D:\Program Files\gfzq'
win7rootXunji = r'E:\DOC\Parallels\WinTools\zd_pazq'
win7rootList = [win10Triton,win10Lixin, win7rootAsus, win7rootXunji, win10Lengend]
# macroot = r'/Users/Johnson/Documents/Johnson/WinTools/zd_pazq'
macroot = r'/Users/Johnson/Documents/Johnson/WinTools/new_tdx2'
macroot_vm = r'/Volumes/VMware Shared Folders/MacTools/WinTools/new_tdx'
xproot = r'E:\DOC\Parallels\WinTools\zd_pazq'


def get_os_path_sep():
    return os.path.sep

    
evalcmdfpath = r'./sina_pandasSelectCmd.txt'.replace('\\',get_os_path_sep())

class GlobalValues:
    # -*- coding: utf-8 -*-

    def __init__(self):
        global initGlobalValue
        if initGlobalValue == 0:
            self._init_()
            initGlobalValue += 1

    def _init_(self):  # 初始化
        global _global_dict
        _global_dict = {}

    def setkey(self, key, value):
        # """ 定义一个全局变量 """
        if isinstance(value,pd.DataFrame):
            value = reduce_memory_usage(value)
        _global_dict[key] = value

    def getkey(self, key, defValue=None):
        # 　　""" 获得一个全局变量,不存在则返回默认值 """
        try:
            return _global_dict[key]
        except KeyError:
            return defValue
    def getkey_status(self, key):
        # """ 定义一个全局变量 """
        return (key in _global_dict.keys())
    def getlist(self):
        # """ 定义一个全局变量 """
        return (_global_dict.keys())



def format_for_print(df,header=True,widths=False,showCount=False,width=0,table=False,limit_show=20):

    # alist = [x for x in set(df.columns.tolist())]
    # cat_col = ['涨停原因类别','category']
    try:
        cat_col = ['category']
        for col in cat_col:
            if col == '涨停原因类别':
                sep_ = '+'
            else:
                sep_ = ';'

            if col in df.columns and len(df) > 1:
                df[col]=df[col].apply(lambda x:str(x).replace('\r','').replace('\n',''))
                log.debug(f'topSort:{counterCategory(df,col,table=True)}')
                topSort=counterCategory(df,col,table=True).split()
                topSort.reverse()
                top_dic={}
                for x in topSort:
                    top_dic[x.split(sep_)[0]]=x
                    # top_dic[x.split(':')[0]]=x.replace(':','')
                # top_key = [x.split(':')[0] for x in topSort]
                # top_value = [x.replace(':','') for x in topSort]
                # sorted_top_dic = dict(sorted(top_dic.items(), key=lambda item: item[1], reverse=False))
                for idx in df.index[:limit_show]:
                    log.debug(f'idx:{idx} idx df.loc[idx][col]: {df.loc[idx][col]}')
                    ca_list = df.loc[idx][col].split(sep_)
                    ca_listB = ca_list.copy()
                    for key in top_dic:
                        if key in ca_list:
                            if ca_listB.index(key) != 0:
                                element_to_move = ca_listB.pop(ca_listB.index(key))
                                ca_listB.insert(0, top_dic[key])

                    if ca_listB !=  ca_list:
                        ca_listC=[('' if c.find(sep_) > 0 else ' ')+c for c in ca_listB]
                        # ca_listD= [x for x in ca_listC if x.find(':') > 0]
                        # list_to_str = "".join([for x in ca_listB if x.find(':') else x+''])
                        list_to_str = "".join(ca_listC)
                        df.loc[idx,col]=list_to_str

        # if 'category' in df.columns and len(df) > 0:
        #     df['category']=df['category'].apply(lambda x:str(x).replace('\r','').replace('\n',''))
        #     topSort=counterCategory(df,'category',table=True).split()
        #     topSort.reverse()
        #     top_dic={}
        #     for x in topSort:
        #         top_dic[x.split(':')[0]]=x
        #         # top_dic[x.split(':')[0]]=x.replace(':','')
        #     # top_key = [x.split(':')[0] for x in topSort]
        #     # top_value = [x.replace(':','') for x in topSort]
        #     # sorted_top_dic = dict(sorted(top_dic.items(), key=lambda item: item[1], reverse=False))
        #     for idx in df.index:
        #         ca_list = df.loc[idx].category.split(';')
        #         ca_listB = ca_list.copy()
        #         for key in top_dic:
        #             if key in ca_list:
        #                 if ca_listB.index(key) != 0:
        #                     element_to_move = ca_listB.pop(ca_listB.index(key))
        #                     ca_listB.insert(0, top_dic[key])

        #         if ca_listB !=  ca_list:
        #             ca_listC=[('' if c.find(':') > 0 else ' ')+c for c in ca_listB]
        #             # ca_listD= [x for x in ca_listC if x.find(':') > 0]
        #             # list_to_str = "".join([for x in ca_listB if x.find(':') else x+''])
        #             list_to_str = "".join(ca_listC)
        #             df.loc[idx,'category']=list_to_str
        else:
            log.info('df is None')
        alist = df.columns.tolist()
        if 'category' in df.columns:
            df['category'] = df['category'].apply(lambda x:str(x)[:16])
        if header:

            table = PrettyTable([''] + alist )
        else:
            table = PrettyTable(field_names=[''] + alist,header=False)

        for row in df[:limit_show].itertuples():  
            if width > 0:
                # col = df.columns.tolist()
                # co_count = len(df.columns)
                # row_str =f'{str(row.Index)},'
                # row_str =f'{str(row.Index)},'
                # # row_str = ''
                # for idx in range(0,len(row)-1):
                #     print(f'idx:{row[idx]}')
                #     # row_str +=f'{str(getattr(row,col[idx]))},'
                #     row_str +=f'{row[idx]},'
                # # row_str +='%s,'%(fill(str(getattr(row,col[-1])).replace(',',';').replace('，',';'),width=width))
                # row_str +='%s,'%(fill(str(row[-1]).replace(',',';').replace('，',';'),width=width))
                # # log.info(f'row_str:{row_str}')
                # # print(row_str.split(','))
                # table.add_row(row_str.split(','))

                row_str = f''
                for idx in range(0,len(row)-1):
                    row_str+=f'row[{idx}],'
                row_str+=f'fill(str(row[-1]),width=width)'
                log.debug(f'row_str:{row_str}')
                table.add_row(eval(row_str))

            else:
                table.add_row(row)

        if not widths:
            # print(f'showCount:{showCount}')
            if showCount:
                count = f'Count:{len(df)}'
                table = str(table)
                table = table + f'\n{count}'
                if table:
                    if 'category' in df.columns:
                        topSort=counterCategory(df,'category',table=table)
                        table = table + f'\n{topSort}'
            return str(table)
        else:
            if isinstance(widths,list):
                table.set_widths(widths)
                # table.get_string()
                # print table.get_widths()
                return str(table)
        return str(table),table.get_widths()

    except Exception as ex:
        # print("Exception on code: {}".format(code)+ os.linesep + traceback.format_exc())
        return Exception("Exception on format_for_print {}".format(len(df))+ os.linesep + traceback.format_exc())    

def format_replce_list(lst, old='volume', new='maxp'):
        lst_n = [new if x==old else x for x in lst]
        return lst_n


def list_replace(lst, old=1, new=10):
    """replace list elements (inplace)"""
    i = -1
    try:
        while True:
            i = lst.index(old, i + 1)
            lst[i] = new
    except ValueError:
        pass


def format_for_print_show(df,columns_format=None,showCount=False,col=None,table=False,noformat=False):
    if columns_format is None:
        columns_format = ct.Monitor_format_trade
    if col is not None and col not in columns_format:
        # columns_format.remove('volume')
        # columns_format.append(col)
        columns_format = format_replce_list(columns_format,old='volume',new=col)
    # if showCount:
    #     # print(f'Count:{len(df)}')
    #     count_string = (f'Count:{len(df)}')
    #     table = format_for_print(df.loc[:, columns_format],count=count_string)
    # else:
    if noformat:
        # table = format_for_print(df,showCount=showCount,table=table,limit_show=50)
        table = format_for_print(df.loc[:, columns_format],showCount=showCount,table=table,limit_show=50)
    else:
        table = format_for_print(df.loc[:, columns_format],showCount=showCount,table=table,limit_show=50)
    return table

def format_for_print2(df):
    table = PrettyTable(list(df.columns))
    for row in df.itertuples():
        table.add_row(row[1:])
    return (table)


hk_js_decode = """
function d(t) {
    var e, i, n, r, a, o, s, l = (arguments,
            864e5), u = 7657, c = [], h = [], d = ~(3 << 30), f = 1 << 30,
        p = [0, 3, 5, 6, 9, 10, 12, 15, 17, 18, 20, 23, 24, 27, 29, 30], m = Math, g = function () {
            var l, u;
            for (l = 0; 64 > l; l++)
                h[l] = m.pow(2, l),
                26 > l && (c[l] = v(l + 65),
                    c[l + 26] = v(l + 97),
                10 > l && (c[l + 52] = v(l + 48)));
            for (c.push("+", "/"),
                     c = c.join(""),
                     i = t.split(""),
                     n = i.length,
                     l = 0; n > l; l++)
                i[l] = c.indexOf(i[l]);
            return r = {},
                e = o = 0,
                a = {},
                u = w([12, 6]),
                s = 63 ^ u[1],
            {
                _1479: T,
                _136: _,
                _200: S,
                _139: k,
                _197: _mi_run
            }["_" + u[0]] || function () {
                return []
            }
        }, v = String.fromCharCode, b = function (t) {
            return t === {}._
        }, N = function () {
            var t, e;
            for (t = y(),
                     e = 1; ;) {
                if (!y())
                    return e * (2 * t - 1);
                e++
            }
        }, y = function () {
            var t;
            return e >= n ? 0 : (t = i[e] & 1 << o,
                o++,
            o >= 6 && (o -= 6,
                e++),
                !!t)
        }, w = function (t, r, a) {
            var s, l, u, c, d;
            for (l = [],
                     u = 0,
                 r || (r = []),
                 a || (a = []),
                     s = 0; s < t.length; s++)
                if (c = t[s],
                    u = 0,
                    c) {
                    if (e >= n)
                        return l;
                    if (t[s] <= 0)
                        u = 0;
                    else if (t[s] <= 30) {
                        for (; d = 6 - o,
                                   d = c > d ? d : c,
                                   u |= (i[e] >> o & (1 << d) - 1) << t[s] - c,
                                   o += d,
                               o >= 6 && (o -= 6,
                                   e++),
                                   c -= d,
                                   !(0 >= c);)
                            ;
                        r[s] && u >= h[t[s] - 1] && (u -= h[t[s]])
                    } else
                        u = w([30, t[s] - 30], [0, r[s]]),
                        a[s] || (u = u[0] + u[1] * h[30]);
                    l[s] = u
                } else
                    l[s] = 0;
            return l
        }, x = function (t) {
            var e, i, n;
            for (t > 1 && (e = 0),
                     e = 0; t > e; e++)
                r.d++,
                    n = r.d % 7,
                (3 == n || 4 == n) && (r.d += 5 - n);
            return i = new Date,
                i.setTime((u + r.d) * l),
                i
        }, S = function () {
            var t, i, a, o, l;
            if (s >= 1)
                return [];
            for (r.d = w([18], [1])[0] - 1,
                     a = w([3, 3, 30, 6]),
                     r.p = a[0],
                     r.ld = a[1],
                     r.cd = a[2],
                     r.c = a[3],
                     r.m = m.pow(10, r.p),
                     r.pc = r.cd / r.m,
                     i = [],
                     t = 0; o = {
                d: 1
            },
                 y() && (a = w([3])[0],
                     0 == a ? o.d = w([6])[0] : 1 == a ? (r.d = w([18])[0],
                         o.d = 0) : o.d = a),
                     l = {
                         day: x(o.d)
                     },
                 y() && (r.ld += N()),
                     a = w([3 * r.ld], [1]),
                     r.cd += a[0],
                     l.close = r.cd / r.m,
                     i.push(l),
                 !(e >= n) && (e != n - 1 || 63 & (r.c ^ t + 1)); t++)
                ;
            return i[0].prevclose = r.pc,
                i
        }, _ = function () {
            var t, i, a, o, l, u, c, h, d, f, p;
            if (s > 2)
                return [];
            for (c = [],
                     d = {
                         v: "volume",
                         p: "price",
                         a: "avg_price"
                     },
                     r.d = w([18], [1])[0] - 1,
                     h = {
                         day: x(1)
                     },
                     a = w(1 > s ? [3, 3, 4, 1, 1, 1, 5] : [4, 4, 4, 1, 1, 1, 3]),
                     t = 0; 7 > t; t++)
                r[["la", "lp", "lv", "tv", "rv", "zv", "pp"][t]] = a[t];
            for (r.m = m.pow(10, r.pp),
                     s >= 1 ? (a = w([3, 3]),
                         r.c = a[0],
                         a = a[1]) : (a = 5,
                         r.c = 2),
                     r.pc = w([6 * a])[0],
                     h.pc = r.pc / r.m,
                     r.cp = r.pc,
                     r.da = 0,
                     r.sa = r.sv = 0,
                     t = 0; !(e >= n) && (e != n - 1 || 7 & (r.c ^ t)); t++) {
                for (l = {},
                         o = {},
                         f = r.tv ? y() : 1,
                         i = 0; 3 > i; i++)
                    if (p = ["v", "p", "a"][i],
                    (f ? y() : 0) && (a = N(),
                        r["l" + p] += a),
                        u = "v" == p && r.rv ? y() : 1,
                        a = w([3 * r["l" + p] + ("v" == p ? 7 * u : 0)], [!!i])[0] * (u ? 1 : 100),
                        o[p] = a,
                    "v" == p) {
                        if (!(l[d[p]] = a) && (s > 1 || 241 > t) && (r.zv ? !y() : 1)) {
                            o.p = 0;
                            break
                        }
                    } else
                        "a" == p && (r.da = (1 > s ? 0 : r.da) + o.a);
                r.sv += o.v,
                    l[d.p] = (r.cp += o.p) / r.m,
                    r.sa += o.v * r.cp,
                    l[d.a] = b(o.a) ? t ? c[t - 1][d.a] : l[d.p] : r.sv ? ((m.floor((r.sa * (2e3 / r.m) + r.sv) / r.sv) >> 1) + r.da) / 1e3 : l[d.p] + r.da / 1e3,
                    c.push(l)
            }
            return c[0].date = h.day,
                c[0].prevclose = h.pc,
                c
        }, T = function () {
            var t, e, i, n, a, o, l;
            if (s >= 1)
                return [];
            for (r.lv = 0,
                     r.ld = 0,
                     r.cd = 0,
                     r.cv = [0, 0],
                     r.p = w([6])[0],
                     r.d = w([18], [1])[0] - 1,
                     r.m = m.pow(10, r.p),
                     a = w([3, 3]),
                     r.md = a[0],
                     r.mv = a[1],
                     t = []; a = w([6]),
                     a.length;) {
                if (i = {
                    c: a[0]
                },
                    n = {},
                    i.d = 1,
                32 & i.c)
                    for (; ;) {
                        if (a = w([6])[0],
                        63 == (16 | a)) {
                            l = 16 & a ? "x" : "u",
                                a = w([3, 3]),
                                i[l + "_d"] = a[0] + r.md,
                                i[l + "_v"] = a[1] + r.mv;
                            break
                        }
                        if (32 & a) {
                            o = 8 & a ? "d" : "v",
                                l = 16 & a ? "x" : "u",
                                i[l + "_" + o] = (7 & a) + r["m" + o];
                            break
                        }
                        if (o = 15 & a,
                            0 == o ? i.d = w([6])[0] : 1 == o ? (r.d = o = w([18])[0],
                                i.d = 0) : i.d = o,
                            !(16 & a))
                            break
                    }
                n.date = x(i.d);
                for (o in {
                    v: 0,
                    d: 0
                })
                    b(i["x_" + o]) || (r["l" + o] = i["x_" + o]),
                    b(i["u_" + o]) && (i["u_" + o] = r["l" + o]);
                for (i.l_l = [i.u_d, i.u_d, i.u_d, i.u_d, i.u_v],
                         l = p[15 & i.c],
                     1 & i.u_v && (l = 31 - l),
                     16 & i.c && (i.l_l[4] += 2),
                         e = 0; 5 > e; e++)
                    l & 1 << 4 - e && i.l_l[e]++,
                        i.l_l[e] *= 3;
                i.d_v = w(i.l_l, [1, 0, 0, 1, 1], [0, 0, 0, 0, 1]),
                    o = r.cd + i.d_v[0],
                    n.open = o / r.m,
                    n.high = (o + i.d_v[1]) / r.m,
                    n.low = (o - i.d_v[2]) / r.m,
                    n.close = (o + i.d_v[3]) / r.m,
                    a = i.d_v[4],
                "number" == typeof a && (a = [a, a >= 0 ? 0 : -1]),
                    r.cd = o + i.d_v[3],
                    l = r.cv[0] + a[0],
                    r.cv = [l & d, r.cv[1] + a[1] + !!((r.cv[0] & d) + (a[0] & d) & f)],
                    n.volume = (r.cv[0] & f - 1) + r.cv[1] * f,
                    t.push(n)
            }
            return t
        }, k = function () {
            var t, e, i, n;
            if (s > 1)
                return [];
            for (r.l = 0,
                     n = -1,
                     r.d = w([18])[0] - 1,
                     i = w([18])[0]; r.d < i;)
                e = x(1),
                    0 >= n ? (y() && (r.l += N()),
                        n = w([3 * r.l], [0])[0] + 1,
                    t || (t = [e],
                        n--)) : t.push(e),
                    n--;
            return t
        };
    return _mi_run = function () {
        var t, i, a, o;
        if (s >= 1)
            return [];
        for (r.f = w([6])[0],
                 r.c = w([6])[0],
                 a = [],
                 r.dv = [],
                 r.dl = [],
                 t = 0; t < r.f; t++)
            r.dv[t] = 0,
                r.dl[t] = 0;
        for (t = 0; !(e >= n) && (e != n - 1 || 7 & (r.c ^ t)); t++) {
            for (o = [],
                     i = 0; i < r.f; i++)
                y() && (r.dl[i] += N()),
                    r.dv[i] += w([3 * r.dl[i]], [1])[0],
                    o[i] = r.dv[i];
            a.push(o)
        }
        return a
    }
        ,
        g()()
}
"""

# def tool_trade_date_hist_sina() -> pd.DataFrame:
#     """
#     交易日历-历史数据
#     https://finance.sina.com.cn/realstock/company/klc_td_sh.txt
#     :return: 交易日历
#     :rtype: pandas.DataFrame
#     """
#     url = "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt"
#     r = requests.get(url)
#     js_code = py_mini_racer.MiniRacer()
#     js_code.eval(hk_js_decode)
#     dict_list = js_code.call(
#         "d", r.text.split("=")[1].split(";")[0].replace('"', "")
#     )  # 执行js解密代码
#     temp_df = pd.DataFrame(dict_list)
#     temp_df.columns = ["trade_date"]
#     temp_df["trade_date"] = pd.to_datetime(temp_df["trade_date"]).dt.date
#     temp_list = temp_df["trade_date"].to_list()
#     temp_list.append(datetime.date(1992, 5, 4))  # 是交易日但是交易日历缺失该日期
#     temp_list.sort()
#     temp_df = pd.DataFrame(temp_list, columns=["trade_date"])
#     return temp_df

# def fetch_stocks_trade_date():
#     try:
#         data = tool_trade_date_hist_sina()
#         if data is None or len(data.index) == 0:
#             return None
#         # data_date = set(data['trade_date'].values.tolist())
#         data_date = (data['trade_date'].values.tolist())
#         return data_date
#     except Exception as e:
#         print(f"stockfetch.fetch_stocks_trade_date处理异常：{e}")
#     return None

# def is_trade_date_old(date=datetime.date.today()):
#     trade_status = GlobalValues().getkey('is_trade_date')
#     if trade_status is None:
#         trade_date = fetch_stocks_trade_date()
#         if trade_date is None:
#             return None
#         if date in trade_date:
#             return True
#         else:
#             return False
#     else:
#         return trade_status
def read_ini(inifile='filter.ini',setrule=None,category='General',filterkey='filter_rule'):
    from configobj import ConfigObj
    baser = getcwd().split('stock')[0]
    base = baser + 'stock' + path_sep
    config_file_path = base + inifile
    setrule = setrule.strip() if setrule is not None else None
    if not os.path.exists(config_file_path):
        # Define the path for the config file
        # --- Writing a config file ---
        config = ConfigObj()
        config.filename = config_file_path

        # Add sections and options
        if category == 'General':
            config[category] = {}
            rule = "top_all.query('boll >=fibl > 1 and red > 1 and close > lastp2d and high > upper')"
            config[category][filterkey] = rule
        else:
            config[category] = {}
            rule = None
            config[category][filterkey] = rule
        # config['General']['version'] = '1.0.0'

        # config['Database'] = {}
        # config['Database']['host'] = 'localhost'
        # config['Database']['port'] = '5432'
        # config['Database']['username'] = 'admin'
        # config['Database']['password'] = 'secure_pass'

        # # Add a section with list values and a root-level option
        # config['Features'] = {}
        # config['Features']['enabled_modules'] = ['logging', 'analytics', 'reporting']
        # config['debug_mode'] = 'True' # Root-level option

        # Write the config object to the file
        config.write()
        print(f"Config file '{config_file_path}' created successfully.")

    else:
        # --- Reading a config file ---
        read_config = ConfigObj(config_file_path)
        # Access values like a dictionary
        if category in read_config.keys():
            if filterkey in read_config[category].keys():
                rule = read_config[category][filterkey]
            else:
                read_config[category][filterkey] = {}
                rule = 'None'
                read_config[category][filterkey] = rule
                read_config.write()
        else:
            read_config[category] = {}
            rule = 'None'
            read_config[category][filterkey] = rule
            read_config.write()
            # print(f"Config file '{config_file_path}' init None")
        # db_host = read_config['Database']['host']
        # enabled_modules = read_config['Features']['enabled_modules']
        # debug_mode = read_config['debug_mode']

        # print(f"\nRead from config file:")
        # print(f"Application Name: {app_name}")
        # print(f"Database Host: {db_host}")
        # print(f"Enabled Modules: {enabled_modules}")
        # print(f"Debug Mode: {debug_mode}")
        if setrule is not None and setrule != 'default':
            read_config[category][filterkey] = setrule
            if rule is not None and rule != 'None':
                read_config[category][f'{filterkey}{get_today("")}'] = rule
            # --- Updating a config file ---
            # read_config['General']['version'] = '1.0.1'
            # read_config['Database']['password'] = 'new_secure_pass'
            read_config.write()
            print(f"Config file '{config_file_path}' updated successfully.")
    if rule.find('top_all') >= 0 or rule.find('top_temp') >= 0:
        rule = rule.replace('top_all.query','').replace('top_temp.query','')
    if rule == 'None':
        rule = None
    if setrule == 'default':
        rule = (f' category:{category} key:{read_config[category].keys()}\n{read_config[category][filterkey]}')
    return rule

def is_trade_date(date=datetime.date.today()):
    trade_status = None
    if isinstance(date, datetime.date):
        date = date.strftime('%Y-%m-%d')
        if date == get_today():
            trade_status = GlobalValues().getkey('is_trade_date')
    if trade_status is None:
        # trade_date = fetch_stocks_trade_date()
        # if trade_date is None:
        #     return None
        # if date in trade_date:
        #     return True
        # else:
        #     return False
        trade_status = get_day_istrade_date(date)
        GlobalValues().setkey('is_trade_date',trade_status)
    return trade_status



def get_last_trade_date(dt=None):
    if dt is None:
        dt = datetime.date.today().strftime('%Y-%m-%d')
    return(a_trade_calendar.get_pre_trade_date(dt))

def get_lastdays_trade_date(days=10):
    if days is None:
        dt = get_last_trade_date()
    else:
        today = datetime.date.today()
        dt = (today + datetime.timedelta(-(days+1))).strftime('%Y-%m-%d')
        duration = a_trade_calendar.get_trade_count(dt,get_today())
        if duration > days:
            for da in range(1,duration-days+1):
                dt =  a_trade_calendar.get_next_trade_date(dt)
        elif duration < days:
            for da in range(1,days-duration+1):
                dt =  a_trade_calendar.get_pre_trade_date(dt)
    return(dt)


def get_day_istrade_date(dt=None):
    #2025
    sep='-'
    if dt is None:
        TODAY = datetime.date.today()
        fstr = "%Y" + sep + "%m" + sep + "%d"
        dt = TODAY.strftime(fstr)
    else:
        if isinstance(dt, datetime.date):
            dt = dt.strftime('%Y-%m-%d')
    is_trade_date = a_trade_calendar.is_trade_date(dt)

    return(is_trade_date)


is_trade_date_today = get_day_istrade_date()
last_trade_date = get_last_trade_date()


def check_file_exist(filepath):
    filestatus=False
    if os.path.exists(filepath):
        filestatus = True
    return filestatus


def getcwd():
    dirname, filename = os.path.split(os.path.abspath(sys.argv[0]))
    return dirname

def get_sys_system():
    return platform.system()

def isMac():
    if get_sys_system().find('Darwin') == 0:
        return True
    else:
        #python2
        # import codecs
        # sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
        return False

def get_run_path_stock(fp=None):
    # path ='c:\\users\\johnson\\anaconda2\\envs\\pytorch_gpu\\lib\\site-packages'
    # root_path='D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\'
    path = getcwd()
    alist = path.split('stock')
    # if len(alist) > 0:
    if len(alist) > 0 and path.find('stock') >=0:
        path = alist[0]
        # os_sep=get_os_path_sep()
        if fp is not None:
            path = path + fp
        log.debug("info:%s getcwd:%s"%(alist[0],path))
    else:
        if isMac():
            path  = root_path[1].split('stock')[0]
            if not check_file_exist(path):
                log.error(f'path not find : {path}')
        else:
            path  = root_path[0].split('stock')[0]
            if not check_file_exist(path):
                log.error(f'path not find : {path}')
        log.debug("error:%s cwd:%s"%(alist[0],path))
    return path


def get_run_path_tdx(fp=None):
    # path ='c:\\users\\johnson\\anaconda2\\envs\\pytorch_gpu\\lib\\site-packages'
    # root_path='D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\'
    path = getcwd()
    alist = path.split('stock')
    # if len(alist) > 0:
    if len(alist) > 0 and path.find('stock') >=0:
        path = alist[0]
        # os_sep=get_os_path_sep()
        if fp is not None:
            path = path + fp + '.h5'
        log.debug("info:%s getcwd:%s"%(alist[0],path))
    else:
        if isMac():
            path  = root_path[1].split('stock')[0] + fp + '.h5'
            if not check_file_exist(path):
                log.error(f'path not find : {path}')
        else:
            path  = root_path[0].split('stock')[0] + fp + '.h5'
            if not check_file_exist(path):
                log.error(f'path not find : {path}')
        log.debug("error:%s cwd:%s"%(alist[0],path))
    return path


tdx_hd5_name = r'tdx_all_df_%s' % (300)
tdx_hd5_path = get_run_path_tdx(tdx_hd5_name)
# win10_ramdisk_root = r'R:'
# mac_ramdisk_root = r'/Volumes/RamDisk'
# ramdisk_rootList = [win10_ramdisk_root, mac_ramdisk_root]
ramdisk_rootList = LoggerFactory.ramdisk_rootList
path_sep = os.path.sep




def get_now_basedir(root_list=[macroot,macroot_vm]):
    basedir=''
    for mpath in root_list:
        if os.path.exists(mpath):
            basedir = mpath
            break
    return basedir


def get_tdx_dir():
    os_sys = get_sys_system()
    os_platform = get_sys_platform()
    if os_sys.find('Darwin') == 0:
        log.info("DarwinFind:%s" % os_sys)
        macbase=get_now_basedir()
        basedir = macbase.replace('/', path_sep).replace('\\', path_sep)
        log.info("Mac:%s" % os_platform)

    elif os_sys.find('Win') == 0:
        log.info("Windows:%s" % os_sys)
        if os_platform.find('XP') == 0:
            log.info("XP:%s" % os_platform)
            basedir = xproot.replace('/', path_sep).replace('\\', path_sep)  # 如果你的安装路径不同,请改这里
        else:
            log.info("Win7O:%s" % os_platform)
            for root in win7rootList:
                basedir = root.replace('/', path_sep).replace('\\', path_sep)  # 如果你的安装路径不同,请改这里
                if os.path.exists(basedir):
                    log.info("%s : path:%s" % (os_platform, basedir))
                    break
    if not os.path.exists(basedir):
        log.error("basedir not exists")
    return basedir


def get_sys_platform():
    return platform.platform()




def get_os_system():
    os_sys = get_sys_system()
    os_platform = get_sys_platform()
    if os_sys.find('Darwin') == 0:
        # log.info("Mac:%s" % os_platform)
        return 'mac'
    elif os_sys.find('Win') == 0:
        # log.info("Windows:%s" % os_sys)
        if os_platform.find('10'):
            return 'win10'

    elif os_sys.find('Win') == 0:
        # log.info("Windows:%s" % os_sys)
        if os_platform.find('XP'):
            return 'winXP'
    else:
        return 'other'

# if get_os_system().find('win') >= 0:
    # import win_unicode_console
#     # https://github.com/Drekin/win-unicode-console
#     win_unicode_console.enable(use_readline_hook=False)

def set_default_encode(code='utf-8'):
        # import sys
        importlib.reload(sys)
        sys.setdefaultencoding(code)
        print((sys.getdefaultencoding()))
        print((sys.stdin.encoding,sys.stdout.encoding))
        


# reload(sys)
# sys.setdefaultencoding('utf8')
# reload(sys)
# sys.setdefaultencoding('cp936')


          
def isDigit(x):
    #re def isdigit()
    try:
        if str(x) == 'nan' or x is None:
            return False
        else:
            float(x)
            return True
    except ValueError:
        return False

def get_ramdisk_dir():
    os_platform = get_sys_platform()
    basedir = None
    for root in ramdisk_rootList:
        basedir = root.replace('/', path_sep).replace('\\', path_sep)
        if os.path.exists(basedir):
            log.info("%s : path:%s" % (os_platform, basedir))
            break
    return basedir

RamBaseDir = get_ramdisk_dir()


def get_ramdisk_path(filename, lock=False):
    if filename:
        basedir = RamBaseDir
        # basedir = ramdisk_root.replace('/', path_sep).replace('\\',path_sep)
        if not os.path.isdir(basedir):
            log.error("ramdisk Root Err:%s" % (basedir))
            return None

        if not os.path.exists(basedir):
            log.error("basedir not exists")
            return None

        if not lock:
            if not filename.endswith('h5'):
                filename = filename + '.h5'
        else:
            if filename.endswith('h5'):
                filename = filename.replace('h5', 'lock')
            else:
                filename = filename + '.lock'

        if filename.find(basedir) >= 0:
            log.info("file:%s" % (filename))
            return filename

        file_path = basedir + path_sep + filename
        # for root in win7rootList:
        #     basedir = root.replace('/', path_sep).replace('\\',path_sep)  # 如果你的安装路径不同,请改这里
        #     if os.path.exists(basedir):
        #         log.info("%s : path:%s" % (os_platform,basedir))
        #         break
    return file_path
# get_ramdisk_path('/Volumes/RamDisk/top_now.h5')


scriptcount = '''tell application "Terminal"
    --activate
    get the count of window
end tell
'''

scriptname = '''tell application "Terminal"
    --activate
    %s the name of window %s
end tell
'''


# title:sina_Market-DurationDn.py
# target rect1:(106, 586, 1433, 998) rect2:(106, 586, 1433, 998)
# title:sina_Market-DurationCXDN.py
# target rect1:(94, 313, 1421, 673) rect2:(94, 313, 1421, 673)
# title:sina_Market-DurationSH.py
# title:sina_Market-DurationUP.py
# target rect1:(676, 579, 1996, 1017) rect2:(676, 579, 1996, 1017)
# title:sina_Monitor-Market-LH.py
# target rect1:(588, 343, 1936, 735) rect2:(588, 343, 1936, 735)
# title:sina_Monitor-Market.py
# title:sina_Monitor.py
# target rect1:(259, 0, 1698, 439) rect2:(259, 0, 1698, 439)
# title:singleAnalyseUtil.py
# target rect1:(1036, 29, 1936, 389) rect2:(1036, 29, 1936, 389)
# title:LinePower.py
# target rect1:(123, 235, 1023, 595) rect2:(123, 235, 1023, 595)
# title:sina_Market-DurationDnUP.py
# title:instock_Monitor.py
# target rect1:(229, 72, 1589, 508) rect2:(229, 72, 1589, 508)


terminal_positionKey4K = {'sina_Market-DurationDn.py': '106, 586,1400,440',
                        'sina_Market-DurationCXDN.py': '94, 313,1400,440',
                        'sina_Market-DurationSH.py': '-29, 623,1400,440',
                        'sina_Market-DurationUP.py': '676, 579,1400,440',
                        'sina_Monitor-Market-LH.py': '588, 343,1400,440',
                        'sina_Monitor-Market.py': '19, 179,1400,440',
                        'sina_Monitor.py': '259, 0,1400, 520',
                        'singleAnalyseUtil.py': '1036, 29,920,360',
                        'LinePower.py': '123, 235,760, 420', 
                        'sina_Market-DurationDnUP.py': '41, 362,1400,440',
                        'instock_Monitor.py':'229, 72,1360,440',
                        'chantdxpower.py':'155, 167, 1200, 480',}



terminal_positionKey1K_triton = {'sina_Market-DurationDn.py': '48, 506,1356,438',
                        'sina_Market-DurationCXDN.py': '13, 310,1356,438',
                        'sina_Market-DurationSH.py': '-29, 623,1400,440',
                        'sina_Monitor-Market-LH.py': '567, 286,1356,407',
                        'sina_Monitor-Market.py': '140, 63,1400,440',
                        'sina_Monitor.py': '109, 20, 1356, 520',
                        'singleAnalyseUtil.py': '1046, 20,897,359',
                        'LinePower.py': '9, 216, 761,407',
                        'sina_Market-DurationDnUP.py': '602,518,1352,464',
                        'sina_Market-DurationUP.py': '48, 506,1353,438',
                        'instock_Monitor.py':'32, 86,1400, 359',
                        'chantdxpower.py':'86, 128, 649,407',
                        'ths-tdx-web.py':'70, 200, 159,27',
                        'pywin32_mouse.py':'70, 200, 159,27',
                        'filter_resample_Monitor.py':'549, 244,1356,520'}



terminal_positionKey2K_R9000P = {'sina_Market-DurationDn.py': '-13, 601,1400,440',
                        'sina_Market-DurationCXDN.py': '-6, 311,1400,440',
                        'sina_Market-DurationSH.py': '-29, 623,1400,440',
                        'sina_Market-DurationUP.py': '445, 503,1400,440',
                        'sina_Monitor-Market-LH.py': '521, 332,1400,420',
                        'sina_Monitor-Market.py': '271, 39,1400,440',
                        'sina_Monitor.py': '108, 1, 1400, 560',
                        'chantdxpower.py': '53, 66,800,420', 
                        'singleAnalyseUtil.py': '673, 0,880,360',
                        'LinePower.py': '6, 216,800,420', 
                        'sina_Market-DurationDnUP.py': '41, 362,1400,480' ,}


''' R9000P 2.5K
title:sina_Market-DurationDn.py
target rect1:(6, 434, 1406, 874) rect2:(6, 434, 1406, 874)
target rect1:(-13, 601, 1387, 1041) rect2:(-13, 601, 1387, 1041)
title:sina_Monitor-Market-LH.py
target rect1:(666, 338, 2067, 758) rect2:(666, 338, 2067, 758)
title:sina_Monitor-Market.py
title:LinePower.py
title:sina_Monitor.py
target rect1:(271, 39, 1671, 479) rect2:(271, 39, 1671, 479)
title:singleAnalyseUtil.py
target rect1:(833, 666, 1713, 1026) rect2:(833, 666, 1713, 1026)
title:sina_Market-DurationCXDN.py
target rect1:(31, 301 1445, 688) rect2:(45, 248, 1445, 688)
title:sina_Market-DurationUp.py
target rect1:(92, 142, 1492, 582) rect2:(92, 142, 1492, 582)
'''



# title:sina_Market-DurationDn.py
# target rect1:(-4, 718, 1396, 1178) rect2:(-4, 718, 1396, 1178)
# title:sina_Monitor-Market-LH.py
# target rect1:(-25600, -25600, -25441, -25573) rect2:(-25600, -25600, -25441, -25573)
# title:sina_Monitor-Market.py
# title:LinePower.py
# title:sina_Monitor.py
# target rect1:(140, 63, 1540, 523) rect2:(140, 63, 1540, 523)
# title:singleAnalyseUtil.py
# target rect1:(554, 406, 1563, 799) rect2:(554, 406, 1563, 799)
# title:sina_Market-DurationCXDN.py
# target rect1:(40, 253, 1440, 713) rect2:(40, 253, 1440, 713)
# title:sina_Market-DurationUp.py
# target rect1:(91, 149, 1491, 609) rect2:(91, 149, 1491, 609)

# terminal_positionKey = {'sina_Market-DurationDn.py': '8, 801',
#                         'sina_Market-DurationCXDN.py': '79, 734',
#                         'sina_Market-DurationSH.py': '-29, 623',
#                         'sina_Market-DurationUp.py': '451, 703',
#                         'sina_Monitor-Market-LH.py': '666, 338',
#                         'sina_Monitor-Market.py': '19, 179',
#                         'sina_Monitor.py': '205, 659',
#                         'singleAnalyseUtil.py': '328, 594',
#                         'LinePower.py': '6, 216', 
#                         'sina_Market-DurationDnUP.py': '6, 434,1400,440' ,}

# terminal_positionKey_all = {'sina_Market-DurationDn.py': '654, 680',
#                         'sina_Market-DurationCXDN.py': '-16, 54',
#                         'sina_Market-DurationSH.py': '-29, 623',
#                         'sina_Market-DurationUp.py': '-22, 89',
#                         'sina_Monitor-Market-LH.py': '666, 338',
#                         'sina_Monitor-Market.py': '19, 179',
#                         'sina_Monitor.py': '28, 23',
#                         'singleAnalyseUtil.py': '1095, 23',
#                         'LinePower.py': '6, 216',
#                         'sina_Market-DurationDnUP.py': '6, 434,1400,440' ,}


# terminal_positionKeyMac2021_OLD = {'sina_Market-DurationDn.py': '186, 506',
#                         'sina_Market-DurationCXDN.py': '39, 126',
#                         'sina_Market-DurationSH.py': '-29, 623',
#                         'sina_Market-DurationUp.py': '0, 394',
#                         'sina_Monitor-Market-LH.py': '184, 239',
#                         'sina_Monitor-Market.py': '19, 179',
#                         'sina_Monitor.py': '116, 58',
#                         'singleAnalyseUtil.py': '594, 23',
#                         'LinePower.py': '6, 216', }

terminal_positionKeyMac2021 = {'sina_Market-DurationDn.py': '541, 530',
                        'sina_Market-DurationCXDN.py': '0, 194',
                        'sina_Market-DurationSH.py': '-29, 623',
                        'sina_Monitor-Market-LH.py': '184, 239',
                        'sina_Market-DurationUP.py': '-13, 406',
                        'sina_Market-DurationDnUP.py' :'171, 361',
                        'sina_Monitor-Market.py': '19, 179',
                        'sina_Monitor.py': '60, 53',
                        'instock_Monitor.py':'18, 119',
                        'singleAnalyseUtil.py': '630, 23',
                        'LinePower.py': '1, 216', }

"""
('sina_Market-DurationDn.py', '541, 530\n')
('sina_Monitor.py', '213, 46\n')
('singleAnalyseUtil.py', '630, 23\n')
('sina_Market-DurationCXDN.py', '-30, 85\n')
('sina_Market-DurationUp.py', '-21, 418\n')
('sina_Market-DurationUp.py', '-21, 418\n')

"""

# terminal_positionKeyMac = {'sina_Market-DurationDn.py': '216, 490',
#                         'sina_Market-DurationCXDN.py': '-16, 54',
#                         'sina_Market-DurationSH.py': '-29, 623',
#                         'sina_Market-DurationUp.py': '-22, 89',
#                         'sina_Monitor-Market-LH.py': '184, 239',
#                         'sina_Monitor-Market.py': '19, 179',
#                         'sina_Monitor.py': '28, 23',
#                         'singleAnalyseUtil.py': '594, 23',
#                         'LinePower.py': '6, 216', }

terminal_positionKey_VM = {'sina_Market-DurationDn.py': '342, 397',
                        'sina_Market-DurationCXDN.py': '84, 222',
                        'sina_Market-DurationSH.py': '-29, 623',
                        'sina_Market-DurationUp.py': '-12, 383',
                        'sina_Monitor-Market-LH.py': '666, 338',
                        'sina_Monitor-Market.py': '19, 179',
                        'sina_Monitor.py': '8, 30',
                        'singleAnalyseUtil.py': '615, 23',
                        'LinePower.py': '6, 216', }

# terminal_positionKey_triton = {'sina_Market-DurationDn.py': '47, 410, 1400, 460',
#                         'sina_Market-DurationCXDN.py': '23, 634,1400,460',
#                         'sina_Market-DurationSH.py': '-29, 623,1400,460',
#                         'sina_Market-DurationUp.py': '330, 464,1400,460',
#                         'sina_Monitor-Market-LH.py': '603, 501, 1400, 420',
#                         'sina_Monitor-Market.py': '19, 179,1400,460',
#                         'sina_Monitor.py': '87, 489,1400,460',
#                         'singleAnalyseUtil.py': '1074, 694,880,360',
#                         'LinePower.py': '1031, 682,800,420',
#                         'instock_Monitor.py':'24, 260,1360,440',}




def get_system_postionKey():
    basedir = get_now_basedir()
    import socket
    hostname = socket.gethostname() 
        # monitors = monitors if len(monitors) > 0 else False
        
    if basedir.find('vm') >= 0:
        positionKey = terminal_positionKey_VM
    elif get_os_system() == 'mac':
        positionKey = terminal_positionKeyMac2021
        # positionKey = cct.terminal_positionKeyMac
    else:
        positionKey = terminal_positionKey4K
        # positionKey = cct.terminal_positionKey1K_triton
    if not isMac():
        if hostname.find('R900') >=0:
            positionKey = terminal_positionKey2K_R9000P
        else:
            ScreenHeight,ScreenWidth = get_screen_resolution()
            if ScreenWidth == '3840':
                positionKey = terminal_positionKey4K
            else:
                positionKey = terminal_positionKey1K_triton

    return positionKey


    
# terminal_positionKey = terminal_positionKey_VM

script_set_position = '''tell application "Terminal"
    --activate
    %s position of window %s to {%s}
end tell
'''

closeterminalw = '''osascript -e 'tell application "Terminal" to close windows %s' '''

scriptquit = '''tell application "Python Launcher" to quit'''


def get_terminal_Position(cmd=None, position=None, close=False, retry=False):
    """[summary]

    [description]

    Keyword Arguments:
        cmd {[type]} -- [description] (default: {None})
        position {[type]} -- [description] (default: {None})
        close {bool} -- [description] (default: {False})

    Returns:
        [type] -- [description]
    """

    if (GlobalValues().getkey('Position') is not None ):
        log.info("Position:%s"%(GlobalValues().getkey('Position')))
        # log.info("Position is locate")
        return 0
    # else:
    #     GlobalValues().setkey('Position',1)

    win_count = 0
    if get_os_system() == 'mac':
        def cct_doScript(scriptn):
            proc = subprocess.Popen(['osascript', '-'],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE)
            stdout_output = proc.communicate(scriptn.encode('utf8'))[0]
            # print stdout_output, type(proc)
            return stdout_output.decode('utf-8')

        if cmd is not None and cmd.find("Python Launcher") >= 0:
            cct_doScript(cmd)
            return win_count

        count = cct_doScript(scriptcount)
        if position is None:
            close_list = []
            if int(count) > 0 and cmd is not None:
                log.info("count:%s" % (count))
                for n in range(1, int(count) + 1):
                    title = cct_doScript(scriptname % ('get', str(object=n)))
                    # log.info("count n:%s title:%s" % (n, title))

                    if title.lower().find(cmd.lower()) >= 0:

                        log.info("WinFind:%s get_title:%s " % (n, title))
                        win_count += 1
                        # print "get:%s"%(n)
                        # position=cct_doScript(script_get_position % ('get', str(n)))
                        if close:
                            close_list.append(n)
                            log.info("close:%s %s" % (n, cmd))
                            # os.system(closeterminalw % (n))
                            # break
                    else:
                        if close:
                            log.info("Title notFind:%s title:%s Cmd:%s" % (n, title.replace('\n', ''), cmd.lower()))
            if len(close_list) > 0:
                if not retry and len(close_list) > 1:
                    sleep(5)
                    get_terminal_Position(cmd=cmd, position=position, close=close, retry=True)
                else:
                    for n in close_list:
                        os.system(closeterminalw % (close_list[0]))
                        log.error("close:%s %s" % (n, cmd))

        else:
            # sleep(1, catch=True)
            position = position.split(os.sep)[-1]
            log.info("position Argv:%s" % (position))
            positionKey = get_system_postionKey()
            if int(count) > 0:
                if position in list(positionKey.keys()):
                    log.info("count:%s" % (count))
                    for n in range(1, int(count) + 1):
                        title = cct_doScript(scriptname % ('get', str(object=n)))
                        if title.lower().find(position.lower()) >= 0:
                            log.info("title find:%s po:%s" % (title, positionKey[position]))
                            position = cct_doScript(script_set_position % ('set', str(n), positionKey[position]))
                            break
                        else:
                            log.info("title not find:%s po:%s" % (title, position))
                else:
                    log.info("Keys not position:%s" % (position))
    return win_count

# get_terminal_Position(cmd=scriptquit, position=None, close=False)
# get_terminal_Position('Johnson — -bash', close=True)
log.info("close Python Launcher")


# from numba.decorators import autojit


def run_numba(func):
    funct = autojit(lambda: func)
    return funct


def get_work_path(base, dpath, fname):

    # baser = os.getcwd().split(base)[0]
    baser = getcwd().split(base)[0]
    base = baser + base + path_sep + dpath + path_sep
    filepath = base + fname
    return filepath


def get_rzrq_code(market='all'):

    baser = getcwd().split('stock')[0]
    base = baser + 'stock' + path_sep + 'JohnsonUtil' + path_sep
    szrz = base + 'szrzrq.csv'
    shrz = base + 'shrzrq.csv'
    if market in ['all', 'sz', 'sh']:
        dfsz = pd.read_csv(szrz, dtype={'code': str}, encoding='gbk')
        if market == 'sz':
            return dfsz
        dfsh = pd.read_csv(shrz, dtype={'code': str}, encoding='gbk')
        dfsh = dfsh.loc[:, ['code', 'name']]
        if market == 'sh':
            return dfsh
        dd = pd.concat([dfsz,dfsh], ignore_index=True)
    elif market == 'cx':
        cxzx = base + 'cxgzx.csv'
        dfot = pd.read_csv(cxzx, dtype={'code': str}, sep='\t', encoding='gbk')
        dd = dfot.loc[:, ['code', 'name']]
    else:
        cxzx = base + market + '.csv'
        dfot = pd.read_csv(cxzx, dtype={'code': str}, sep='\t', encoding='gbk')
        dd = dfot.loc[:, ['code', 'name']]
    print("rz:%s" % (len(dd)), end=' ')
    return dd


def get_tushare_market(market='zxb', renew=False, days=5):
    def tusharewrite_to_csv(market, filename, days):
        import tushare as ts
        if market == 'zxb':
            df = ts.get_sme_classified()
        elif market == 'captops':
            df = ts.cap_tops(days).loc[:, ['code', 'name']]
            if days != 10:
                initda = days * 2
                df2 = ts.inst_tops(initda).loc[:, ['code', 'name']]
                df = pd.concat([df,df2])
                df.drop_duplicates('code', inplace=True)
        else:
            log.warn('market not found')
            return pd.DataFrame()
        if len(df) > 0:
            df = df.set_index('code')
        else:
            log.warn("get error")
        df.to_csv(filename, encoding='gbk')
        log.warn("update %s :%s" % (market, len(df))),
        df.reset_index(inplace=True)
        return df

    baser = getcwd().split('stock')[0]
    base = baser + 'stock' + path_sep + 'JohnsonUtil' + path_sep
    filepath = base + market + '.csv'
    if os.path.exists(filepath):
        if renew and creation_date_duration(filepath) > 0:
            df = tusharewrite_to_csv(market, filepath, days)
        else:
            df = pd.read_csv(filepath, dtype={'code': str}, encoding='gbk')
            # df = pd.read_csv(filepath,dtype={'code':str})
            if len(df) == 0:
                df = tusharewrite_to_csv(market, filepath, days)
    else:
        df = tusharewrite_to_csv(market, filepath, days)

    return df

sina_doc = """sina_Johnson.

Usage:
  sina_xxx.py
  sina_xxx.py [-d <debug>]

Options:
  -h --help     Show this screen.
  -d <debug>    [default: error].
"""

sina_doc_old = """sina_Johnson.

Usage:
  sina_cxdn.py
  sina_cxdn.py --debug
  sina_cxdn.py --de <debug>

Options:
  -h --help     Show this screen.
  --debug       Debug [default: error].
  --de=<debug>    [default: error].
"""
# --info    info [default:False].


def sys_default_utf8(default_encoding='utf-8'):
    #import sys
    #    default_encoding = 'utf-8'
    if sys.getdefaultencoding() != default_encoding:
        importlib.reload(sys)
        sys.setdefaultencoding(default_encoding)

sys_default_utf8()


def get_tdx_dir_blocknew():
    blocknew_path = get_tdx_dir() + r'/T0002/blocknew/'.replace('/', path_sep).replace('\\', path_sep)
    return blocknew_path

def get_tdx_dir_blocknew_dxzq(block_path):

    blocknew_path = get_tdx_dir_blocknew()
    if block_path.find(blocknew_path) > -1:
        blkname = block_path.split('\\')[-1]
        blocknew_path = win10dxzq + r'/T0002/blocknew/'.replace('/', path_sep).replace('\\', path_sep) + blkname
    else:
        log.error("not find blkname{block_path}")
    return blocknew_path



def get_screen_resolution():
    proc = subprocess.Popen(['powershell', 'Get-WmiObject win32_desktopmonitor;'], stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    res = proc.communicate()
    # monitorsName = re.findall('(?s)\r\nName\s+:\s(.*?)\r\n', res[0].decode("gbk"))
    # monitorsName = re.findall('\r\nName\s+:\s(.*?)\r\n', res[0].decode("gbk"))
    # monitorScreenWidth = re.findall('\r\nScreenWidth\s+:\s(.*?)\r\n', res[0].decode("gbk"))
    # monitorScreenHeight = re.findall('\r\nScreenHeight\s+:\s(.*?)\r\n', res[0].decode("gbk"))
    # for screenWidth in monitorScreenWidth:
    #     # if screenWidth == '3840':
    #     if isDigit(screenWidth):
    #         return screenWidth
    # return 0
    
    if len(res) > 10:
        ScreenHeight,ScreenWidth = re.findall('\r\nScreenHeight\s+:\s(.*?)\r\nScreenWidth\s+:\s(.*?)\r\n', res[0].decode("gbk"))[-1]
    else:
        ScreenHeight,ScreenWidth = '1080','1920'
    return ScreenHeight,ScreenWidth 


def check_chinese(checkstr):
    status = re.match('[ \\u4e00 -\\u9fa5]+', checkstr) == None
    return status
# def whichEncode(text):
#   text0 = text[0]
#   try:
#     text0.decode('utf8')
#   except Exception, e:
#     if "unexpected end of data" in str(e):
#       return "utf8"
#     elif "invalid start byte" in str(e):
#       return "gbk_gb2312"
#     elif "ascii" in str(e):
#       return "Unicode"
#   return "utf8"



from chardet import detect
# get file encoding type
def get_encoding_type(file):
    with open(file, 'rb') as f:
        rawdata = f.read()
    return detect(rawdata)['encoding']

# open(current_file, 'r', encoding = get_encoding_type, errors='ignore')
# str = unicode(str, errors='replace')
# or
# str = unicode(str, errors='ignore')

# I had same problem with UnicodeDecodeError and i solved it with this line.
# Don't know if is the best way but it worked for me.
# str = str.decode('unicode_escape').encode('utf-8')




def getCoding(strInput):
    '''
    获取编码格式
    '''
    if isinstance(strInput, str):
        return "unicode"
    try:
        strInput.decode("utf8")
        return 'utf8'
    except:
        pass
    try:
        strInput.decode("gbk")
        return 'gbk'
    except:
        pass
    try:
        strInput.decode("utf16")
        return 'utf16'
    except:
        pass


def tran2UTF8(strInput):
    '''
    转化为utf8格式
    '''
    strCodingFmt = getCoding(strInput)
    if strCodingFmt == "utf8":
        return strInput
    elif strCodingFmt == "unicode":
        return strInput.encode("utf8")
    elif strCodingFmt == "gbk":
        return strInput.decode("gbk").encode("utf8")


def tran2GBK(strInput):
    '''
    转化为gbk格式
    '''
    strCodingFmt = getCoding(strInput)
    if strCodingFmt == "gbk":
        return strInput
    elif strCodingFmt == "unicode":
        return strInput.encode("gbk")
    elif strCodingFmt == "utf8":
        return strInput.decode("utf8").encode("gbk")

def get_file_size(path_to_file):
    # filesize = os.path.getsize(path_to_file) / 1000 / 1000
    if os.path.exists(path_to_file):
        filesize = os.path.getsize(path_to_file)
    else:
        filesize = 0
    return filesize





def creation_date_duration(path_to_file):
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    # if platform.system() == 'Windows':
    #     return os.path.getctime(path_to_file)
    # else:
    #     stat = os.stat(path_to_file)
    #     try:
    #         return stat.st_birthtime
    #     except AttributeError:
    #         # We're probably on Linux. No easy way to get creation dates here,
    #         # so we'll settle for when its content was last modified.
    #         return stat.st_mtime
    if os.path.exists(path_to_file):
        dt = os.path.getmtime(path_to_file)
        dtm = datetime.date.fromtimestamp(dt)
        today = datetime.date.today()
        duration = (today - dtm).days
    else:
        duration = 0
    return duration

def filepath_datetime(path_to_file):
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    # if platform.system() == 'Windows':
    #     return os.path.getctime(path_to_file)
    # else:
    #     stat = os.stat(path_to_file)
    #     try:
    #         return stat.st_birthtime
    #     except AttributeError:
    #         # We're probably on Linux. No easy way to get creation dates here,
    #         # so we'll settle for when its content was last modified.
    #         return stat.st_mtime
    if os.path.exists(path_to_file):
        dt = os.path.getmtime(path_to_file)
        dtm = datetime.date.fromtimestamp(dt)
    else:
        dtm = datetime.datetime.now().timestamp()
    return dtm


if not isMac():
    import win32api,win32gui
import _thread

def get_window_pos(targetTitle):  
    hWndList = []  
    win32gui.EnumWindows(lambda hWnd, param: param.append(hWnd), hWndList)  
    for hwnd in hWndList:
        clsname = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if (title.find(targetTitle) >= 0):    #调整目标窗口到坐标(600,300),大小设置为(600,600)
            rect1 = win32gui.GetWindowRect(hwnd)
            # rect2 = get_window_rect(hwnd)
            # rect2 = rect1
            # print("targetTitle:%s rect1:%s rect2:%s"%(title,rect1,rect1))
            print(("target rect1:%s rect2:%s"%(rect1,rect1)))
            # win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 330,678,600,600, win32con.SWP_SHOWWINDOW)
            # win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 330,678,600,600, win32con.SWP_SHOWWINDOW)
            # win32gui.MoveWindow(hwnd,1026, 699, 900, 360,True)  #108,19

def reset_window_pos(targetTitle,posx=1026,posy=699,width=900,height=360,classsname='ConsoleWindowClass'):

    hWndList = []  
    win32gui.EnumWindows(lambda hWnd, param: param.append(hWnd), hWndList)
    status=0  
    # time.sleep(0.2)
    try:
        for hwnd in hWndList:
            clsname = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
            # log.error("title:%s"%(title))
            if (clsname == classsname  and title.find(targetTitle) == 0):    #调整目标窗口到坐标(600,300),大小设置为(600,600)
                rect1 = win32gui.GetWindowRect(hwnd)
                # rect2 = get_window_rect(hwnd)
                # log.debug("targetTitle:%s rect1:%s rect2:%s"%(title,rect1,rect1))
                # win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 330,678,600,600, win32con.SWP_SHOWWINDOW)
                # win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 330,678,600,600, win32con.SWP_SHOWWINDOW)
                win32gui.MoveWindow(hwnd,int(posx), int(posy), int(width), int(height),True)  #108,19
                status +=1

    except Exception as e:
        print(f'Exception:{e}')
    finally:
        pass

def set_ctrl_handler():
    # os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'
    # def doSaneThing(sig, func=None):
    # '''忽略所有KeyCtrl'''
    # return True
    # win32api.SetConsoleCtrlHandler(doSaneThing, 1)

    def handler(dwCtrlType, hook_sigint=_thread.interrupt_main):
        print(("ctrl:%s" % (dwCtrlType)))
        if dwCtrlType == 0:  # CTRL_C_EVENT
            # hook_sigint()
            # raise KeyboardInterrupt("CTRL-C!")
            return 1  # don't chain to the next handler
        return 0  # chain to the next handler
    win32api.SetConsoleCtrlHandler(handler, 1)

def set_clear_logtime(time_t=1):
    h5_fname = 'sina_MultiIndex_data'
    h5_table = 'all' + '_' + str(ct.sina_limit_time)
    fname = 'sina_logtime'
    logtime = get_config_value_ramfile(fname)
    write_t = get_config_value_ramfile(fname,currvalue=time_t,xtype='time',update=True)


#将字典里的键全部由大写转换为小写
def capital_to_lower(dict_info):
    new_dict = {}
    for i, j in list(dict_info.items()):
        new_dict[i.lower()] = j
    return new_dict

    # before_dict = {'ABC': 'python', 'DEF': 'java', 'GHI': 'c', 'JKL': 'go'}
    # print capital_to_lower(before_dict)

#将字典里的键全部由小写转换为大写

def lower_to_capital(dict_info):
    new_dict = {}
    for i, j in list(dict_info.items()):
        new_dict[i.upper()] = j
    return new_dict


def set_console(width=80, height=15, color=3, title=None, closeTerminal=True):
    # mode con cp select=936
    # os.system("mode con: cols=%s lines=%s"%(width,height))
    # print os.path.splitext(sys.argv[0])
    if title is None:
        # title= (os.path.basename(sys.argv[0]))
        filename = (os.path.basename(sys.argv[0]))
        log.debug(f'filename:{filename}')
    elif isinstance(title, list):
        filename = (os.path.basename(sys.argv[0]))
        for cname in title:
            # print cname
            filename = filename + ' ' + str(cname)
            log.debug(f'filename:{filename}')
            # print filename
    else:
        filename = (os.path.basename(sys.argv[0])) + ' ' + title
        log.debug(f'filename:{filename}')

    if isMac():
        # os.system('printf "\033]0;%s\007"'%(filename))
        if title is None:
            os.system('printf "\e[8;%s;%st"' % (height, width))
        # printf "\033]0;%s sin ZL: 356.8 To:183 D:3 Sh: 1.73%  Vr:3282.4-3339.7-2.6%  MR: 4.3 ZL: 356.8\007"
        filename = filename.replace('%', '!')
        os.system('printf "\033]0;%s\007"' % (filename))
    else:
        # os.system('title=%s' % sys.argv[0])
        os.system('title=%s' % filename)
        log.debug(f'filename:{filename}')
        # win32MoveCom.reset_window_pos(title,width=width,height=height)
        # os.system("mode con cols=%s lines=25"%(width))   #windowsfg
        # os.system("mode con cols=%s lines=%s"%(width,height))   #windowsfg
        # os.system("mode con cols=120 lines=2000"%(width,height))   #windowsfg
        # os.system('mode %s,%s'%(width,height))
    # printf "\033]0;My Window title\007”
    # os.system('color %s'%color)
    # set_ctrl_handler()

    # if (GlobalValues().getkey('Position') is not None ):
    #     print("Position:%s"%(cct.GlobalValues().getkey('Position')))
    #     log.info("Position is locate")
    #     return 0
    # else:
    #     GlobalValues().setkey('Position',1)

    if closeTerminal and (GlobalValues().getkey('Position') is None):
        GlobalValues().setkey('Position',1)

        # get_terminal_Position(cmd=scriptquit, position=None, close=False)
        if isMac():
            get_terminal_Position(position=filename)
        else:
            
            title= (os.path.basename(sys.argv[0]))
            positionKey=capital_to_lower(get_system_postionKey())
            # positionKey=capital_to_lower(terminal_positionKey1K_triton)
            log.debug(f'positionKey:{positionKey}')
            if title.lower() in list(positionKey.keys()) or title.replace('exe','py').lower() in list(positionKey.keys()):
                # log.error("title.lower() in positionKey.keys()")
                log.debug(f'title:{title.lower()}')
                if title.lower() in list(positionKey.keys()) or title.replace('exe','py').lower() in list(positionKey.keys()):
                    if title.find('.exe') >=0:
                        pos=positionKey[title.replace('exe','py').lower()].split(',')
                    else:
                        pos=positionKey[title.lower()].split(',') 
                else:
                    pos= '254, 674,1400,420'.split(',')
                    log.error("pos is none")
                log.info("pos:%s title:%s Position:%s"%(pos,title,GlobalValues().getkey('Position')))
                # cct.get_window_pos('sina_Market-DurationUp.py')
                # cct.reset_window_pos(key,pos[0],pos[1],pos[2],pos[3])

                status=reset_window_pos(title,pos[0],pos[1],pos[2],pos[3])
                log.debug("reset_window_pos-status:%s"%(status))
            else:
                log.error("%s not in terminal_positionKey_triton"%(title))
        # (os.path.basename(sys.argv[0]))
        # get_terminal_Position(clean_terminal[1], close=True)
    # else:
        # log.error("closeTerminal:%s title:%s Position:%s"%(closeTerminal,title,GlobalValues().getkey('Position')))

def timeit_time(cmd, num=5):
    import timeit
    time_it = timeit.timeit(lambda: (cmd), number=num)
    print(("timeit:%s" % time_it))


def get_delay_time():
    delay_time = 8000
    return delay_time


def cct_raw_input(sts):
    # print sts
    if sys.getrecursionlimit() < 2000:
        sys.setrecursionlimit(2000)
    if GlobalValues().getkey('Except_count') is None:
        GlobalValues().setkey('Except_count', 0)
        log.info("recursionlimit:%s"%(sys.getrecursionlimit()))

    st = ''
    time_s = time.time()
    count_Except = GlobalValues().getkey('Except_count')
    try:
        # if get_os_system().find('win') >= 0:
            # win_unicode_console.disable()
        # https://stackoverflow.com/questions/11068581/python-raw-input-odd-behavior-with-accents-containing-strings
        # st = win_unicode_console.raw_input.raw_input(sts)
        st = input(sts)
        # issubclass(KeyboardInterrupt, BaseException)
    # except (KeyboardInterrupt, BaseException) as e:
    except (KeyboardInterrupt, BaseException) as e:
        # inputerr = cct_raw_input(" Break: ")
        # if inputerr == 'e' or inputerr == 'q':
        #     sys.exit(0)
        # # raise Exception('raw interrupt')
        # if inputerr is not None and len(inputerr) > 0:
        #     return inputerr
        # else:
        #     return ''
        # count_Except = GlobalValues().getkey('Except_count')
        if count_Except is not None and count_Except < 3:
            count_Except = count_Except + 1
            GlobalValues().setkey('Except_count', count_Except)
            # sys.exit()
            # print "cct_raw_input:ExceptionError:%s count:%s" % (e, count_Except)
            # st = cct_raw_input(sts)
        else:
            # print "cct_ExceptionError:%s count:%s" % (e, count_Except)
            log.error("count_Except > 2")
            GlobalValues().setkey('Except_count', 0)
            # if get_os_system().find('win') >= 0:
            #     win_unicode_console.enable(use_readline_hook=False)
            # raise KeyboardInterrupt()
            sys.exit()

    except (IOError, EOFError, Exception) as e:
        # count_Except = GlobalValues().getkey('Except_count')
        if count_Except is not None and count_Except < 3:
            count_Except = count_Except + 1
            GlobalValues().setkey('Except_count', count_Except)
            # sys.exit()
            # print "cct_raw_input:ExceptionError:%s count:%s" % (e, count_Except)
            # st = cct_raw_input(sts)
        else:
            print("cct_ExceptionError:%s count:%s" % (e, count_Except))
            log.error("cct_ExceptionError:%s count:%s" % (e, count_Except))
            sys.exit()
    # except ValueError as e:
    #     raise Exception('Invalid Exception: {}'.format(e)) from None
    # if get_os_system().find('win') >= 0:
        # win_unicode_console.enable(use_readline_hook=False)
    t1 = time.time() - time_s
    if t1 < 0.2 and count_Except is not None and count_Except < 3:
        time.sleep(0.2)
        count_Except = count_Except + 1
        GlobalValues().setkey('Except_count', count_Except)
        st = 'no Input'
    time.sleep(0.1)
    return st.strip()

# eval_rule = "[elem for elem in dir() if not elem.startswith('_') and not elem.startswith('ti')]"
# eval_rule = "[elem for elem in dir() if not elem.startswith('_')]"
eval_rule = "[elem for elem in dir() if elem.startswith('top') or elem.startswith('block') or elem.startswith('du') ]"



#MacOS arrow keys history auto complete
if isMac():
    import readline
    import rlcompleter, readline
    # readline.set_completer(completer.complete)
    readline.parse_and_bind('tab:complete')


class MyCompleter(object):  # Custom completer

    def __init__(self, options):
        self.options = sorted(options)

    def complete(self, text, state):
        if state == 0:  # on first trigger, build possible matches
            if text:  # cache matches (entries that start with entered text)
                # self.matches = [s for s in self.options
                #                     if s and s.startswith(text)]
                self.matches = [s for s in self.options
                                if text in s]
            else:  # no text entered, all matches possible
                self.matches = self.options[:]

        # return match indexed by state
        try:
            return self.matches[state]
        except IndexError:
            return None


def cct_eval(cmd):
    try:
        st = eval(cmd)
    except (Exception) as e:
        st = ''
        print(e)
    return st

GlobalValues().setkey('Except_count', 0)

def custom_sleep(sleep=5):

    time_set = sleep  # 计时设定时间
    SYSJ = None  # 剩余时间
    start_time = time.time()
    while True:
        t1 = time.time() - start_time  # 计时时间间隔
        SYSJ = time_set - t1  # 剩余时间
        # print("t1:%s du:%s"%(t1,SYSJ))
        # m, s = divmod(SYSJ, 60)  # 获取分， 秒
        # h, m = divmod(m, 60)  # 获取小时，分
        if SYSJ > 0:
            pass
            # print("%02d:%02d:%02d" % (h, m, s))  #正常打印
            # print("\r%02d:%02d:%02d" % (h, m, s),end="")  # 每次把光标定位到行首，打印
        else:
            # print(u"\n计时结束")
            break
    # print "start:%s"%(time.time()-start_time)
# custom_sleep(0.5)

def sleep(timet, catch=True):
    times = time.time()
    log.info('sleep:%s'%(timet))
    loop_status = 1
    try:
        # log.info("range(int(timet) * 2):%s"%(range(int(timet) * 2)))
        # for _ in range(int(timet) * 2):
        count_s = 0
        while loop_status:
            loop_status = 0
            time.sleep(0.2)
            # custom_sleep(0.5)
            t1 = time.time() - times
            duration = t1 - timet
            if duration >= 0 :
                break
            else:
                count_s +=1
                loop_status = 1
                # if count_s%10 == 0:
                #     log.info("sleep10:%s"%(int(time.time() - times) - int(timet))) 
            # log.info('sleeptime:%s'%(int(time.time() - times)))
        log.info('break sleeptime:%s'%(int(time.time() - times)))
    except (KeyboardInterrupt) as e:
        # raise KeyboardInterrupt("CTRL-C!")
        # print "Catch KeyboardInterrupt"
        if catch:
            raise KeyboardInterrupt("Sleep Time")
        else:
            print("KeyboardInterrupt Sleep Time")

    except (IOError, EOFError, Exception) as e:
        count_Except = GlobalValues().getkey('Except_count')
        if count_Except is not None and count_Except < 3:
            GlobalValues().setkey('Except_count', count_Except + 1)
            print("cct_raw_input:ExceptionError:%s count:%s" % (e, count_Except))
        else:
            print("cct_ExceptionError:%s count:%s" % (e, count_Except))
            # sys.exit(0)

    finally:
        log.info('cct_Exception finally loop_status:%s'%(loop_status))
        # raise Exception("code is None")
    # print time.time()-times


def sleeprandom(timet):
    now_t = get_now_time_int()
    if now_t > 915 and now_t < 926:
        sleeptime = random.randint(int(10 / 3), 5)
    else:
        sleeptime = random.randint(int(timet / 3), int(timet))
    if get_work_duration():
        print("Error2sleep:%s" % (sleeptime))
        sleep(sleeptime, False)
    else:
        sleep(sleeptime)


def get_cpu_count():
    return cpu_count()



def day8_to_day10(start, sep='-'):
    if start:
        start = str(start)
        if len(start) == 8:
            if start.find(':') < 0:
                start = start[:4] + sep + start[4:6] + sep + start[6:]
    return start


def get_time_to_date(times, format='%H:%M'):
    # time.gmtime(times) 世界时间
    # time.localtime(times) 本地时间
    return time.strftime(format, time.localtime(times))


def get_today(sep='-'):
    TODAY = datetime.date.today()
    fstr = "%Y" + sep + "%m" + sep + "%d"
    today = TODAY.strftime(fstr)
    return today

    # from dateutil import rrule

    # def workdays(start, end, holidays=0, days_off=None):
    # start=datetime.datetime.strptime(start,'%Y-%m-%d')
    # end=datetime.datetime.strptime(end,'%Y-%m-%d')
    # if days_off is None:
    # days_off = 0, 6
    # workdays = [x for x in range(7) if x not in days_off]
    # print workdays
    # days = rrule.rrule(rrule.DAILY, start, until=end, byweekday=workdays)
    # return days
    # return days.count() - holidays


def get_work_day_status():
    today = datetime.datetime.today().date()
    day_n = int(today.strftime("%w"))

    if day_n > 0 and day_n < 6:
        return True
    else:
        return False
    # return str(today)
def get_work_day_idx():
    today = datetime.datetime.today().date()
    day_n = int(today.strftime("%w"))
    # if 0 < day_n < 6:
    #     return day_n
    # else:
    #     return 5
    return day_n

def last_tddate(days=1):
    # # today = datetime.datetime.today().date() + datetime.timedelta(-days)
    # if days is None:
    #     return days
    # dt = GlobalValues().getkey(f'last_tddate-{days}')
    # if dt is None:
    #     today = datetime.date.today()
    #     if days == 1:
    #     # dt = today + datetime.timedelta(days-1)
    #         dt = today.strftime('%Y-%m-%d')
    #         dt = get_last_trade_date(dt)
    #         GlobalValues().setkey(f'last_tddate-{days}',dt)
    #         log.debug(f'setkey:last_tddate-{days} : {dt}')
    #     else:
    #         # dt = (today + datetime.timedelta(-(days-1))).strftime('%Y-%m-%d')
    #         # # dt = datetime.date.today().strftime('%Y-%m-%d')
    #         # dt = get_last_trade_date(dt)
    #         dt = get_lastdays_trade_date(days)
    #         GlobalValues().setkey(f'last_tddate-{days}',dt)
    #         log.debug(f'setkey:last_tddate-{days} : {dt}')

    return get_lastdays_trade_date(days)
   
# def last_tddate(days=1):
#     # today = datetime.datetime.today().date() + datetime.timedelta(-days)
#     if days is None:
#         return days
#     today = datetime.datetime.today().date()
#     log.debug("today:%s " % (today))
#     # return str(today)

#     def get_work_day(today):
#         day_n = int(today.strftime("%w"))
#         if day_n == 0:
#             lastd = today + datetime.timedelta(-2)
#             log.debug("0:%s" % lastd)
#         elif day_n == 1:
#             lastd = today + datetime.timedelta(-3)
#             log.debug("1:%s" % lastd)
#         else:
#             lastd = today + datetime.timedelta(-1)
#             log.debug("2-6:%s" % lastd)
#         # is_trade_date()
#         return lastd
#         # if days==0:
#         # return str(lasd)
#     lastday = today
#     for x in range(int(days)):
#         # print x
#         lastday = get_work_day(today)
#         today = lastday
#     return str(lastday)

    '''
    oday = lasd - datetime.timedelta(days)
    day_n = int(oday.strftime("%w"))
    # print oday,day_n
    if day_n == 0:
        # print day_last_week(-2)
        return str(datetime.datetime.today().date() + datetime.timedelta(-2))
    elif day_n == 6:
        return str(datetime.datetime.today().date() + datetime.timedelta(-1))
    else:
        return str(oday)
    '''

# def is_holiday(date):
#     if isinstance(date, str):
#         date = datetime.datetime.strptime(date, '%Y-%m-%d')
#     today=int(date.strftime("%w"))
#     if today > 0 and today < 6 and date not in holiday:
#         return False
#     else:
#         return True


def day_last_days(daynow,last=-1):
    return str(datetime.datetime.strptime(daynow, '%Y-%m-%d').date() + datetime.timedelta(last))

def day_last_week(days=-7):
    lasty = datetime.datetime.today().date() + datetime.timedelta(days)
    return str(lasty)


def is_holiday(date):
    if isinstance(date, str):
        date = datetime.datetime.strptime(date, '%Y-%m-%d')
    today = int(date.strftime("%w"))
    if today > 0 and today < 6 and date not in holiday:
        return False
    else:
        return True


def testdf(df):
    if df is not None and len(df) > 0:
        pass
    else:
        pass


def testdf2(df):
    if df is not None and not df.empty:
        pass
    else:
        pass


def get_today_duration(datastr, endday=None,tdx=False):
    if datastr is not None and len(datastr) > 6:
        if endday:
            today = datetime.datetime.strptime(day8_to_day10(endday), '%Y-%m-%d').date()
        else:
            if tdx and ((is_trade_date_today and get_now_time_int() < 1500) or not is_trade_date_today) and datastr == last_trade_date:
                return 0 
                # today = last_trade_date
            else:
                today = datetime.date.today()
        # if get_os_system() == 'mac':
        #     # last_day = datetime.datetime.strptime(datastr, '%Y/%m/%d').date()
        #     last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
        # else:
        #     # last_day = datetime.datetime.strptime(datastr, '%Y/%m/%d').date()
        #     last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
        last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
        
        duration_day = int((today - last_day).days)
    else:
        duration_day = None
    return (duration_day)


def get_now_time():
    # now = time.time()
    # now = time.localtime()
    # # d_time=time.strftime("%Y-%m-%d %H:%M:%S",now)
    # d_time = time.strftime("%H:%M", now)
    d_time = datetime.datetime.now().strftime("%H:%M")

    return d_time


def get_now_time_int():
    now_t = datetime.datetime.now().strftime("%H%M")
    return int(now_t)


def get_work_time(now_t = None):
    # return True
    # now_t = str(get_now_time()).replace(':', '')
    # now_t = int(now_t)
    if get_trade_date_status() == 'False':
        return False
    if now_t == None:
        now_t = get_now_time_int()
    if not get_work_day_status():
        return False
    if (now_t > 1132 and now_t < 1300) or now_t < 915 or now_t > 1502:
        return False
        # return True
    else:
        # if now_t > 1300 and now_t <1302:
            # sleep(random.randint(5, 120))
        return True

def get_work_time_duration():
    if get_trade_date_status() == 'False':
        return False
    now_t = get_now_time_int()
    if  now_t < 915 or now_t > 1502:
        return False
    else:
        return True


def get_work_hdf_status():
    now_t = str(get_now_time()).replace(':', '')
    now_t = int(now_t)
    if not get_work_day_status():
        return False
    # if (now_t > 1130 and now_t < 1300) or now_t < 915 or now_t > 1502:
    if 915 < now_t < 1502:
        # return False
        return True
    return False


def get_work_duration():
    int_time = get_now_time_int()
    # now_t = int(now_t)
    if get_work_day_status() and ((700 < int_time < 915) or (1132 < int_time < 1300)):
        # if (int_time > 830 and int_time < 915) or (int_time > 1130 and int_time < 1300) or (int_time > 1500 and int_time < 1510):
        # return False
        return True
    else:
        return False


def get_work_time_ratio(resample='d'):
    initx = 3.5
    stepx = 0.5
    init = 0
    initAll = 10
    now = time.localtime()
    ymd = time.strftime("%Y:%m:%d:", now)
    hm1 = '09:30'
    hm2 = '13:00'
    all_work_time = 14400
    d1 = datetime.datetime.now()
    now_t = int(datetime.datetime.now().strftime("%H%M"))
    # d2 = datetime.datetime.strptime('201510111011','%Y%M%d%H%M')
    if now_t > 915 and now_t <= 930:
        d2 = datetime.datetime.strptime(ymd + '09:29', '%Y:%m:%d:%H:%M')
        d1 = datetime.datetime.strptime(ymd + '09:30', '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 1
        ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 930 and now_t <= 1000:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 1
        ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1000 and now_t <= 1030:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 2
        ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1030 and now_t <= 1100:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 3
        ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1100 and now_t <= 1130:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 4
        ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1130 and now_t < 1300:
        init += 4
        ratio_t = 0.5 / (initx + init * stepx) * initAll
    elif now_t >= 1500 or now_t < 930:
        ratio_t = 1.0
    elif now_t > 1300 and now_t <= 1330:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 5
        ratio_t = round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1330 and now_t <= 1400:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 6
        ratio_t = round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1400 and now_t <= 1430:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 7
        ratio_t = round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    else:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        ratio_t = round((ds + 7200) / all_work_time, 3)

    # work_day = get_work_day_idx() 
    # work_day = work_day-3 if work_day > 2 else work_day
    if resample == '3d':
        ratio_t /= 3 
    elif resample == 'w':
        ratio_t /= 5 
    elif resample == 'm':
        ratio_t /= 20

    return ratio_t


def decode_bytes_type(data):
    if isinstance(data,bytes):
        try:
            data = data.decode('utf8')
        except:
            data = data.decode('gbk')
    return data


    
global ReqErrorCount
ReqErrorCount = 1
def get_url_data_R(url, timeout=15,headers=None):
    # headers = {'User-Agent':'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.6) Gecko/20091201 Firefox/3.5.6'}
    # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; rv:16.0) Gecko/20100101 Firefox/16.0',
    #            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    #            'Connection': 'keep-alive'}
    
    # dictMerged2 = dict( dict1, **dict2 )
    # headersrc = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    #        'Connection': 'keep-alive'}

    if headers is None:
        # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; rv:16.0) Gecko/20100101 Firefox/16.0',
        #            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        #            'Connection': 'keep-alive'}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
                   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                   'Connection': 'keep-alive'}
    # else:

    #     headers = dict({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    #                'Connection': 'keep-alive'},**headers)

               # 'Referer':'http://vip.stock.finance.sina.com.cn'
    # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    #             'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    #             'Accept-Encoding': 'gzip, deflate',
    #             }
    # headers = {'Host': 'dcfm.eastmoney.com',
    #             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    #             'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    #             'Accept-Encoding': 'gzip, deflate',
    #             'Connection': 'keep-alive',
    #             'Cookie': 'qgqp_b_id=91b04a5f938180fcd61ff487773f9fdd; st_si=44229608519229; st_sn=17; st_psi=20200422151145626-113300300968-3614946978; st_asi=delete; emshistory=%5B%22%E8%9E%8D%E8%B5%84%E4%BD%99%E9%A2%9D617%22%2C%22%E8%9E%8D%E8%B5%84%E4%BD%99%E9%A2%9D%22%5D; cowCookie=true; intellpositionL=1380px; intellpositionT=1085px; st_pvi=50723143362736; st_sp=2020-04-22%2013%3A25%3A58; st_inirUrl=http%3A%2F%2Figuba.eastmoney.com%2F2822094037475512'
    #         }           
               
    req = Request(url, headers=headers)
    req.keep_alive = False
    try:
        fp = urlopen(req, timeout=timeout)
        data = fp.read()
        fp.close()
    # except (HTTPError, URLError) as error:
        # log.error('Data of %s not retrieved because %s\nURL: %s', name, error, url)
    except (socket.timeout, socket.error) as e:
        # print data.encoding
        data = ''
        log.error('socket timed out error:%s - URL %s ' % (e, url))
        if str(e).find('HTTP Error 456') >= 0:
            sleeprandom(10)
            return data
        sleeprandom(30)
        return data
    except Exception as e:
        data = ''
        log.error('url Exception Error:%s - URL %s ' % (e, url))
        # sleeprandom(60)
        sleep(30)
    else:
        log.info('Access successful.')

    if isinstance(data,bytes):
        try:
            data = data.decode('utf8')
        except:
            data = data.decode('gbk')
    return data

# import urllib.request
# import urllib.error
# import time

def urlopen_with_retry(url, max_retries=3, initial_delay=1):
    """
    Opens a URL with retry logic and exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            response = urlopen(url, timeout=10) # Set a timeout
            return response
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"Attempt {attempt + 1} failed for {url}: {e}")
            if attempt < max_retries - 1:
                delay = initial_delay * (2 ** attempt)
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"Max retries reached for {url}.")
                raise # Re-raise the last exception if all retries fail

    # # Usage example
    # try:
    #     data = urlopen_with_retry("http://www.example.com")
    #     print("Successfully opened URL.")
    #     # Process data
    #     # ...
    # except Exception as e:
    #     print(f"Failed to open URL after retries: {e}")

def get_url_data(url, retry_count=2, pause=0.05, timeout=30, headers=None):
    #    headers = {'User-Agent':'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.6) Gecko/20091201 Firefox/3.5.6'}
    # sina'Referer':'http://vip.stock.finance.sina.com.cn'

    if headers is None:
        # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; rv:16.0) Gecko/20100101 Firefox/16.0',
        #            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        #            'Connection': 'keep-alive'}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
                   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                   'Connection': 'keep-alive'}
    # else:

    #     headers = dict({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    #                'Connection': 'keep-alive'},**headers)

    global ReqErrorCount
    # requests.adapters.DEFAULT_RETRIES = 5 # 增加重连次数
    s = requests.session()
    s.encoding = 'gbk'
    s.keep_alive = False # 关闭多余连接
    for _ in range(retry_count):
        time.sleep(pause)
        try:
            data = s.get(url, headers=headers, timeout=timeout,allow_redirects=False)
        except (socket.timeout, socket.error) as e:
            data = ''
            log.error('socket timed out error:%s - URL %s ' % (e, url))
            if str(e).find('HTTP Error 456') >= 0:
                return data
            if ReqErrorCount < 3:
                ReqErrorCount +=1
                sleeprandom(60)
            else:
                break
        except Exception as e:
            log.error('url Exception Error:%s - URL %s ' % (e, url))
            if ReqErrorCount < 3:
                ReqErrorCount +=1
                sleeprandom(60)
            else:
                break
        else:
            log.info('Access successful.')
        # print data.text
        # fp = urlopen(req, timeout=5)
        # data = fp.read()
        # fp.close()
        # print data.encoding
            return data.text
    #     else:
    #         return df
    print("url:%s" % (url))
    return ''
    # raise IOError(ct.NETWORK_URL_ERROR_MSG)


def get_div_list(ls, n):
    # if isinstance(codeList, list) or isinstance(codeList, set) or
    # isinstance(codeList, tuple) or isinstance(codeList, pd.Series):

    if not isinstance(ls, list) or not isinstance(n, int):
        return []
    ls_len = len(ls)
    if n <= 0 or 0 == ls_len:
        return []
    if n > ls_len:
        return ls
    elif n == ls_len:
        return [[i] for i in ls]
    else:
        # j = (ls_len / n) + 1
        j = int((ls_len / n))
        k = ls_len % n
        # print "K:",k
        ls_return = []
        z = 0
        for i in range(0, (int(n) - 1) * j, j):
            if z < k:
                # if i==0:
                #     z+=1
                #     ls_return.append(ls[i+z*1-1:i+j+z*1])
                #     print i+z*1-1,i+j+z*1
                # else:
                z += 1
                ls_return.append(ls[i + z * 1 - 1:i + j + z * 1])
                # print i+z*1-1,i+j+z*1
            else:
                ls_return.append(ls[i + k:i + j + k])
                # print i+k,i + j+k
        # print (n - 1) * j+k,len(ls)
        ls_return.append(ls[(n - 1) * j + k:])
        return ls_return




def flatten(x):
    result = []
    for el in x:
        if isinstance(x, collections.abc.Iterable) and not isinstance(el, str):
            result.extend(flatten(el))
        else:
            result.append(el)
    return result

def to_asyncio_run_py2(urllist, cmd):
    results = []

    # print "asyncio",
    @asyncio.coroutine
    def get_loop_cmd(cmd, url_s):
        loop = asyncio.get_event_loop()
        result = yield From(loop.run_in_executor(None, cmd, url_s))
        results.append(result)

    threads = []
    for url_s in urllist:
        threads.append(get_loop_cmd(cmd, url_s))
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(asyncio.wait(threads))
    return results

def to_asyncio_run(urllist, cmd):
    results = []

    async def sync_to_async(val):
        return val

    async def get_loop_cmd(cmd, url_s):
        loop = asyncio.get_event_loop()
        # result = yield From(loop.run_in_executor(None, cmd, url_s))
        # result = await cmd(url_s)
        result = await sync_to_async(cmd(url_s))
        results.append(result)

        # response = await aiohttp.get(self.sina_stock_api + self.stock_list[index])
        # response.encoding = self.encoding
        # data = await response.text()

    threads = []
    for url_s in urllist:
        threads.append(get_loop_cmd(cmd, url_s))
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(asyncio.wait(threads))
    return results

def to_mp_run(cmd, urllist):
    # n_t=time.time()
    print("mp:%s" % len(urllist), end=' ')

    pool = ThreadPool(cpu_count())
    # pool = ThreadPool(2)
    # pool = ThreadPool(4)
    print(cpu_count())
    # pool = multiprocessing.Pool(processes=8)
    # for code in codes:
    #     results=pool.apply_async(sl.get_multiday_ave_compare_silent_noreal,(code,60))
    # result=[]
    # results = pool.map(cmd, urllist)
    results = []
    for y in tqdm(pool.imap_unordered(cmd, urllist),unit='%',mininterval=ct.tqpm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols):
        results.append(y)
    # for code in urllist:
    # result.append(pool.apply_async(cmd,(code,)))

    pool.close()
    pool.join()
    results = flatten(results)
    # print "time:MP", (time.time() - n_t)
    return results






def to_mp_run_tqdm_err(cmd, urllist,*args,**kwargs):
    #no work map tqdm
    # n_t=time.time()
    print("mp:%s" % len(urllist), end=' ')

    # pool = ThreadPool(2)
    # pool = ThreadPool(4)
    cpu_used = int(cpu_count()/2)
    print(cpu_count(),cpu_use)

    pool = ThreadPool(processes=cpu_used)
    # for code in codes:
    #     results=pool.apply_async(sl.get_multiday_ave_compare_silent_noreal,(code,60))

    # def worker(cmd,urllisttq):
    #     # for i in tqdm(range(100), desc=f'Worker {num}'):
    #     func = partial(cmd, **kwargs)
    #     resultstq = []   
    #     for y in tqdm(pool.imap_unordered(func, urllisttq),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols):
    #         resultstq.append(y)
    #     return resultstq

    # with multiprocessing.Pool(4) as p:
    #     p.map(worker, [1, 2, 3, 4])


    result=[]
    # kwargs['cmd']=cmd
    # workerfunc = partial(worker, **kwargs)
    # results = pool.map(workerfunc, urllist)
    # for y in tqdm(pool.imap_unordered(func, urllisttq),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols):
    func = partial(cmd, **kwargs)
    for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols):
            result.append(y)


    # results = []
    # for y in tqdm(pool.imap_unordered(cmd, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols):
    #     results.append(y)

    # for code in urllist:
    # result.append(pool.apply_async(cmd,(code,)))

    pool.close()
    pool.join()
    # results = flatten(results)
    # print "time:MP", (time.time() - n_t)
    return results

# from multiprocessing import Pool

def imap_tqdm(function, iterable, processes, chunksize=5, desc=None, disable=False, **kwargs):
    """
    Run a function in parallel with a tqdm progress bar and an arbitrary number of arguments.
    Results are always ordered and the performance should be the same as of Pool.map.
    :param function: The function that should be parallelized.
    :param iterable: The iterable passed to the function.
    :param processes: The number of processes used for the parallelization.
    :param chunksize: The iterable is based on the chunk size chopped into chunks and submitted to the process pool as separate tasks.
    :param desc: The description displayed by tqdm in the progress bar.
    :param disable: Disables the tqdm progress bar.
    :param kwargs: Any additional arguments that should be passed to the function.
    """ 
    if kwargs:
        function_wrapper = partial(_wrapper, function=function, **kwargs)
    else:
        function_wrapper = partial(_wrapper, function=function)

    results = [None] * len(iterable)
    # results = []
    with ThreadPool(processes=processes) as p:
        # with tqdm(desc=desc, total=len(iterable), disable=disable) as pbar:
        with tqdm(desc=desc, total=len(iterable), disable=disable,mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols) as pbar:
            for i, result in p.imap_unordered(function_wrapper, enumerate(iterable), chunksize=chunksize):
                results[i] = result
                # results.append(result)
                pbar.update()

    return results


def _wrapper(enum_iterable, function, **kwargs):
    i = enum_iterable[0]
    result = function(enum_iterable[1], **kwargs)
    return i, result


from functools import partial
from multiprocessing import Pool
def to_mp_run_async_old2025(cmd, urllist, *args,**kwargs):
    # https://stackoverflow.com/questions/68065937/how-to-show-progress-bar-tqdm-while-using-multiprocessing-in-python
    #other  apply the as_completed 
    '''
    import tqdm
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import pandas as pd
    import os

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        # total argument for tqdm is just the number of submitted tasks:
        with tqdm.tqdm(total=len(date)) as progress_bar:
            futures = {}
            for idx, dt in enumerate(date):
                future = executor.submit(create_data, dt)
                futures[future] = idx
            results = [None] * len(date) # pre_allocate slots
            for future in as_completed(futures):
                idx = futures[future] # order of submission
                results[idx] = future.result()
                progress_bar.update(1) # advance by 1
        data = [ent for sublist in results for ent in sublist]
        data = pd.DataFrame(data, columns = cols)
    '''
    # if len(urllist) > 150:
    #     pool_count = (cpu_count()-2)
    # else:
    #     pool_count = 2
    result = []  
    time_s = time.time()

    if len(urllist) > 200:
        if int(round(len(urllist)/100,0)) < 2:
            cpu_co = 1
        else:
            cpu_co = int(round(len(urllist)/100,0))
        cpu_used = int(cpu_count()/2) - 1 
        log.debug(f'count:{len(urllist)} cpu_co:{cpu_co}')
        pool_count = (cpu_used) if cpu_co > (cpu_used) else cpu_co
        # pool_count = (cpu_count()-2) if cpu_co > (cpu_count()-2) else cpu_co
        if  cpu_co > 1 and 1300 < get_now_time_int() < 1500:
            pool_count = int(cpu_count() / 2) - 1
        if len(kwargs) > 0 :
                # pool = ThreadPool(12)
                log.debug(f'cmd:{cmd} kwargs:{kwargs}')
                func = partial(cmd, **kwargs)
                # TDXE:44.26  cpu 1   
                # for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=5):
                # results = pool.map(func, urllist)
                # try:
                #     for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols):
                #         results.append(y)
                # except Exception as e:
                #     log.error("except:%s"%(e))
                try:
                    with Pool(processes=pool_count) as pool:
                        data_count=len(urllist)
                        progress_bar = tqdm(total=data_count)
                        # print("mapping ...")
                        log.debug(f'data_count:{data_count}')
                        # tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols)
                        results = tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count)
                        # print("running ...")
                        result = tuple(results)  # fetch the lazy results

                    #debug:
                    # results=[]
                    # for code in urllist:
                    #     print("code:%s "%(code), end=' ')
                    #     res=cmd(code,**kwargs)
                    #     print("status:%s\t"%(len(res)), end=' ')
                    #     results.append(res)
                    # result=results
                except Exception as e:
                    log.error("except:%s"%(e))
                    traceback.print_exc()
                    # log.error("except:results%s"%(results[-1]))
                    # import ipdb;ipdb.set_trace()
                    results=[]
                    for code in urllist:
                        print(f"code:{code},count:{len(urllist)} idx:{urllist.index(code)}", end=' ')
                        res=cmd(code,**kwargs)
                        print("status:%s\t"%(len(res)), end=' ')
                        results.append(res)
                    result=results
        else:

            try:
                with Pool(processes=pool_count) as pool:
                    data_count=len(urllist)
                    progress_bar = tqdm(total=data_count)
                    # print("mapping ...")
                    # tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols)
                    results = tqdm(pool.imap_unordered(cmd, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count)
                    # print("running ...")
                    result=tuple(results)  # fetch the lazy results
                    # print("done")
            except Exception as e:
                log.error("except:%s"%(e))


    else:
        if len(kwargs) > 0 :
            pool = ThreadPool(1)
            func = partial(cmd, **kwargs)
            # TDXE:40.63  cpu 1    cpu_count() 107.14
            # for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=5):
            # results = pool.map(func, urllist)
            try:
                results = pool.map(func, urllist)
            except Exception as e:
                log.error("except:%s"%(e))
        else:
            pool = ThreadPool(int(cpu_count())/ 2 - 1 if int(cpu_count()) > 2 else 2)
            for code in urllist:
                try:
                    # result = pool.apply_async(cmd, (code,) + args).get()
                    results.append(pool.apply_async(cmd, (code,) + args).get())
                except Exception as e:
                    log.error("except:%s code:%s"%(e,code))
        pool.close()
        pool.join()
        result=results
    print("time:%s"%(round(time.time()-time_s,2)),)
    return result


def process_file_exc(func=None,code=None):
    # partialfunc=GlobalValues().getkey('partialfunc')
    try:
        # if func is None:
        #     return Exception("func is None code: {}".format(code))
        # log.debug(f'code:{code},func:{func}')
        return func(code)
    except Exception as ex:
        # print("Exception on code: {}".format(code)+ os.linesep + traceback.format_exc())
        return Exception("Exception on code {}".format(code)+ os.linesep + traceback.format_exc())



def to_mp_run_async(cmd, urllist, *args,**kwargs):
    # https://stackoverflow.com/questions/68065937/how-to-show-progress-bar-tqdm-while-using-multiprocessing-in-python
    result = []  
    time_s = time.time()
    # func = partial(cmd, **kwargs)
    # module = importlib.import_module(cmd)
    # https://stackoverflow.com/questions/72766345/attributeerror-cant-pickle-local-object-in-multiprocessing
    urllist = list(set(urllist))
    data_count =len(urllist)
    if data_count > 200:
        if int(round(data_count/100,0)) < 2:
            cpu_co = 1
        else:
            cpu_co = int(round(data_count/100,0))
        cpu_used = int(cpu_count()/2)  + 1
        # cpu_used = int(cpu_count()) - 2
        pool_count = (cpu_used) if cpu_co > (cpu_used) else cpu_co
        log.debug(f'count:{data_count} pool_count:{pool_count} cpu_co:{cpu_co}')
        # pool_count = (cpu_count()-2) if cpu_co > (cpu_count()-2) else cpu_co
        if  cpu_co > 1 and 1300 < get_now_time_int() < 1500:
            pool_count = int(cpu_count() / 2) + 1
            # pool_count = int(cpu_count()) - 3
        if len(kwargs) > 0 :
                # pool = ThreadPool(12)
                log.debug(f'cmd:{cmd} kwargs:{kwargs}')
                func = partial(cmd, **kwargs)
                partialfunc = partial(process_file_exc, func)
                # GlobalValues().setkey('partialfunc',func)
                # partialfunc=GlobalValues().getkey('partialfunc')
                # print(f"func getkey:{partialfunc('000002')}")

                # TDXE:44.26  cpu 1   
                # for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=data_count,ncols=5):
                # results = pool.map(func, urllist)
                # try:
                #     for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=data_count,ncols=ct.ncols):
                #         results.append(y)
                # except Exception as e:
                #     log.error("except:%s"%(e))

                try:
                    progress_bar = tqdm(total=data_count)
                    log.debug(f'data_count:{data_count},mininterval:{ct.tqdm_mininterval},ncols={ct.ncols}')
                    from tqdm.contrib.concurrent import process_map
                    # from multiprocessing import Manager
                    # manager = Manager()
                    # shared_list = manager.list()
                    # https://stackoverflow.com/questions/67957266/python-tqdm-process-map-append-list-shared-between-processes

                    # tqdm.monitor_interval = 0
                    results = process_map(partialfunc, urllist, unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count,max_workers=pool_count)
                    result = []
                    # for data in results:
                    #     if isinstance(data, Exception):
                    #         print("Got exception: {}".format(data))
                    #     else:
                    #         # print("Got OK result: {}".format(result))
                    #         if len(data) > 10:
                    #             result.append(data)
                    #         else:
                    #             log.error(f'data is None,last code:{result[-1].code}')
                    index_couts = len(results[0].index) if len(results[0]) > 10 else len(results[1].index)
                    log.debug(f'index_couts:{index_couts}')
                    for idx, data in enumerate(results):
                        if isinstance(data, Exception):
                            print("Got exception: {}".format(data))
                        else:
                            # print("Got OK result: {}".format(result))
                            # if len(data) > 0 and len(data.index) == index_couts:
                            if len(data) > 0:
                                result.append(data)
                            else:
                                # log.error(f'idx:{idx} is None,last code:{result[-1].code} resultCount:{len(result)}')
                                log.error(f'idx:{idx} is None, code: {urllist[idx]} CountAll:{data_count} resultCount:{len(result)}')

                    # result = list(set(result))
                    log.debug(f'result:{len(result)}')
                            
                except Exception as e:
                    log.error("except:%s"%(e))
                    traceback.print_exc()
                    # log.error("except:results%s"%(results[-1]))
                    # import ipdb;ipdb.set_trace()
                    results=[]
                    for code in urllist:
                        print(f"code:{code},count:{data_count} idx:{urllist.index(code)}", end=' ')
                        res=cmd(code,**kwargs)
                        print("status:%s\t"%(len(res)), end=' ')
                        results.append(res)
                    result=results
                
                '''
                try:
                    with Pool(processes=pool_count) as pool:
                        data_count=len(urllist)
                        progress_bar = tqdm(total=data_count)
                        # print("mapping ...")

                        log.debug(f'data_count:{data_count},mininterval:{ct.tqdm_mininterval},ncols={ct.ncols}')
                        # tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols)
                        print(f"{os.getpid()=}")
                        # results = tqdm(pool.imap_unordered(partialfunc, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count)
                        
                        # from tqdm.contrib.concurrent import process_map
                        # tqdm.monitor_interval = 0
                        # results = process_map(partialfunc, urllist, unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count,max_workers=pool_count)

                        # print("running ...")
                        # result = tuple(results)  # fetch the lazy results
                        result = []
                        for data in results:
                            if isinstance(data, Exception):
                                print("Got exception: {}".format(data))
                            else:
                                # print("Got OK result: {}".format(result))
                                result.append(data)

                        pool.close()
                        pool.join()
                '''
                    #debug:
                    # results=[]
                    # for code in urllist:
                    #     print("code:%s "%(code), end=' ')
                    #     res=cmd(code,**kwargs)
                    #     print("status:%s\t"%(len(res)), end=' ')
                    #     results.append(res)
                    # result=results
                
        else:

            try:
                with Pool(processes=pool_count) as pool:
                    data_count=len(urllist)
                    progress_bar = tqdm(total=data_count)
                    # print("mapping ...")
                    # tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols)
                    results = tqdm(pool.imap_unordered(cmd, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count)
                    # print("running ...")
                    result=tuple(results)  # fetch the lazy results
                    # print("done")
            except Exception as e:
                log.error("except:%s"%(e))


    else:
        if len(kwargs) > 0 :
            pool = ThreadPool(1)
            func = partial(cmd, **kwargs)
            # TDXE:40.63  cpu 1    cpu_count() 107.14
            # for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=5):
            # results = pool.map(func, urllist)
            try:
                results = pool.map(func, urllist)
            except Exception as e:
                log.error("except:%s"%(e))
        else:
            pool = ThreadPool(int(cpu_count())/ 2 - 1 if int(cpu_count()) > 2 else 2)
            for code in urllist:
                try:
                    # result = pool.apply_async(cmd, (code,) + args).get()
                    results.append(pool.apply_async(cmd, (code,) + args).get())
                except Exception as e:
                    log.error("except:%s code:%s"%(e,code))
        pool.close()
        pool.join()
        result=results
    print("time:%s"%(round(time.time()-time_s,2)),)
    return result



def to_mp_run_async_outdate2023(cmd, urllist, *args,**kwargs):
    # n_t=time.time()
    # print "mp_async:%s" % len(urllist),
    # print "a!!!!:",status

    # n_t = time.time()
    results = []
    # stock_list = []
    # pool_count = (cpu_count()-2)
    pool_count = 1
    time_s = time.time()

    # max_num = 850
    # request_num = len(urllist) // max_num
    # for range_start in range(request_num):
    #     num_start = max_num * range_start
    #     num_end = max_num * (range_start + 1)
    #     request_list = urllist[num_start:num_end]
    #     stock_list.append(request_list)
    # # print len(self.stock_with_exchange_list), num_endzzzzzzzzzz
    # if len(urllist) > num_end:
    #     request_list = urllist[num_end:]
    #     stock_list.append(request_list)
    #     request_num += 1

    # results=to_mp_run_tqdm(cmd,stock_list, *args,**kwargs)

    # imap_tqdm
    # func = partial(cmd, **kwargs)
    # result = imap_tqdm(cmd, urllist,processes=pool_count,**kwargs)

    # results = flatten(results)


    # '''
    
    if len(urllist) > 50:
        if len(kwargs) > 0 :
            pool = ThreadPool(1)
            # pool = ThreadPool(12)
            func = partial(cmd, **kwargs)
            # TDXE:44.26  cpu 1   
            # for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=5):
            # results = pool.map(func, urllist)
            try:
                for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols):
                    results.append(y)
            except Exception as e:
                log.error("except:%s"%(e))
        else:
            pool = ThreadPool(cpu_count())
            # log.error("to_mp_run args is not None")
            for inx in tqdm(list(range(len(urllist))),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols):
                code = urllist[inx]
            # for code in urllist:
                try:
                    # result = pool.apply_async(cmd, (code,) + args).get()
                    results.append(pool.apply_async(cmd, (code,) + args).get())
                except Exception as e:
                    log.error("except:%s code:%s"%(e,code))

    else:
        if len(kwargs) > 0 :
            pool = ThreadPool(1)
            func = partial(cmd, **kwargs)
            # TDXE:40.63  cpu 1    cpu_count() 107.14
            # for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=5):
            # results = pool.map(func, urllist)
            try:
                results = pool.map(func, urllist)
            except Exception as e:
                log.error("except:%s"%(e))
        else:
            pool = ThreadPool(cpu_count())
            for code in urllist:
                try:
                    # result = pool.apply_async(cmd, (code,) + args).get()
                    results.append(pool.apply_async(cmd, (code,) + args).get())
                except Exception as e:
                    log.error("except:%s code:%s"%(e,code))
    pool.close()
    pool.join()
    # '''
    print("time:%s"%(round(time.time()-time_s,2)),)
    return results


def f_print(lens, datastr, type=None):
    data = ('{0:%s}' % (lens)).format(str(datastr))
    if type is not None:
        if type == 'f':
            return float(data)
    else:
        return data


def read_last_lines(filename, lines=1):
    # print the last line(s) of a text file
    """
    Argument filename is the name of the file to print.
    Argument lines is the number of lines to print from last.
    """
    block_size = 1024
    block = ''
    nl_count = 0
    start = 0
    fsock = open(filename, 'rb')
    try:
        # seek to end
        fsock.seek(0, 2)
        # get seek position
        curpos = fsock.tell()
        # print curpos
        while (curpos > 0):  # while not BOF
            # seek ahead block_size+the length of last read block
            curpos -= (block_size + len(block))
            if curpos < 0:
                curpos = 0
            
            # except:'gbk' codec can't decode byte 0xc5 in position 1021:
            # tdx 4107: len(codeList) > 150: 

            fsock.seek(curpos)
            # read to end
            block = fsock.read()
            if isinstance(block,bytes):
                block = block.decode(errors="ignore")
            nl_count = block.count('\n') - block.count('\n\n')
            # nl_count_err = block.count('\n\n')
            # nl_count = nl_count - nl_count_err

            # if read enough(more)
            if nl_count >= lines:
                break
        # get the exact start position
        for n in range(nl_count - lines):
            start = block.find('\n', start) + 1
    finally:
        fsock.close()
    return block[start:]


def _write_to_csv(df, filename, indexCode='code'):
    TODAY = datetime.date.today()
    CURRENTDAY = TODAY.strftime('%Y-%m-%d')
    #     reload(sys)
    #     sys.setdefaultencoding( "gbk" )
    df = df.drop_duplicates(indexCode)
    # df = df.set_index(indexCode)
    # print df[['code','name']]
    df.to_csv(CURRENTDAY + '-' + filename + '.csv',
              encoding='gbk', index=False)  # 选择保存
    print(("write csv:%s" % (CURRENTDAY + '-' + filename + '.csv')))
    # df.to_csv(filename, encoding='gbk', index=False)


def code_to_tdxblk(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST[code]
    else:
        if len(code) != 6:
            return ''
        else:
            # return '1%s' % code if code[:1] in ['5', '6'] else '0%s' % code
            if  code[:1] in ['5', '6']:
                code = '1%s' % code
            elif  code[:2] in ['43','83','87','92']:
                # startswith('43','83','87','92')
                code = '2%s' % code
            else:
                code = '0%s' % code
            return code


def tdxblk_to_code(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST[code]
    else:
        if len(code) != 7:
            return ''
        else:
            return code[1:] if code[:1] in ['1', '0'] else code

def code_to_symbol_dfcf(code):
    """
        生成symbol代码标志
    """
    # if code in ct.INDEX_LABELS:
    #     return ct.INDEX_LIST_TDX[code]
    # else:
    if len(code) != 6:
        return ''
    else:
        return '1.%s' % code if code[:1] in ['5', '6', '9'] else '0.%s' % code


def code_to_index(code):
    if not code.startswith('999') or not code.startswith('399'):
        if code[:1] in ['5', '6', '9']:
            code2 = '999999'
        elif code[:1] in ['3']:
            code2 = '399006'
        else:
            code2 = '399001'
    return code2


def code_to_symbol(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST_TDX[code]
    else:
        if len(code) != 6:
            return ''
        else:
            # return 'sh%s' % code if code[:1] in ['5', '6', '9'] else 'sz%s' % code
            # if  code[:1] in ['5', '6', '9']:
            if  code[:1] in ['5', '6']:
                code = 'sh%s' % code
            elif  code[:2] in ['43','83','87','92']:
                # startswith('43','83','87','92')
                code = 'bj%s' % code
            else:
                code = 'sz%s' % code
            return code

def code_to_symbol_ths(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST_TDX[code]
    else:
        if len(code) != 6:
            return ''
        else:
            if  code[:1] in ['5', '6', '9']:
                code = '%s.SH' % code
            # elif  code[:1] in ['8']:
            elif  code[:2] in ['43','83','87','92']:
                code = '%s.BJ' % code
            else:
                code = '%s.SZ' % code
            return code
            # return '%s.SH' % code if code[:1] in ['5', '6', '9'] else '%s.SZ' % code

def symbol_to_code(symbol):
    """
        生成symbol代码标志
    """
    if symbol in ct.INDEX_LABELS:
        return ct.INDEX_LIST[symbol]
    else:
        if len(symbol) != 8:
            return ''
        else:
            return re.findall('(\d+)', symbol)[0]


def code_to_tdx_blk(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST[code]
    else:
        if len(code) != 6:
            return ''
        else:
            if  code[:1] in ['5', '6']:
                code = '1%s' % code
            elif  code[:2] in ['43','83','87','92']:
                # startswith('43','83','87','92')
                code = '2%s' % code
            else:
                code = '0%s' % code
            return code
            # return '1%s' % code if code[:1] in ['5', '6'] else '0%s' % code


def get_config_value(fname, classtype, currvalue=0, limitvalue=1, xtype='limit', read=False):
    conf_ini = fname
    currvalue = int(float(currvalue))
    # conf_ini = cct.get_work_path('stock','JSONData','count.ini')
    if os.path.exists(conf_ini):
        # log.info("file ok:%s"%conf_ini)
        config = ConfigObj(conf_ini, encoding='UTF8')
        if not read:
            if classtype in list(config.keys()) and xtype in config[classtype].keys():
                if int(float(config[classtype][xtype])) > currvalue:
                    ratio = float(config[classtype][xtype]) / limitvalue
                    if ratio < 1.2:
                        log.info("f_size:%s < read_limit:%s ratio:%0.2f" % (currvalue, config[classtype][xtype], ratio))
                    else:
                        config[classtype][xtype] = limitvalue
                        config.write()
                        log.info("f_size:%s < read_limit:%s ratio < 2 ratio:%0.2f" % (currvalue, config[classtype][xtype], ratio))
                        
                else:

                    log.info("file:%s f_size:%s > read_limit:%s" % (fname, currvalue, config[classtype][xtype][:5]))
                    config[classtype][xtype] = limitvalue
                    config.write()
                    return True
            else:
                # log.error("no type:%s f_size:%s" % (classtype, currvalue))
                config[classtype] = {}
                config[classtype][xtype] = limitvalue
                config.write()
        else:
            if classtype in list(config.keys()) and xtype in config[classtype].keys():
                return config[classtype][xtype]
            else:
                return None
    else:
        config = ConfigObj(conf_ini, encoding='UTF8')
        config[classtype] = {}
        config[classtype][xtype] = limitvalue
        config.write()
    return False


def get_config_value_ramfile(fname, currvalue=0, xtype='time', update=False,cfgfile='h5config.txt',readonly=False,int_time=False):
    classtype = fname
    conf_ini = get_ramdisk_dir() + os.path.sep+ cfgfile
    if xtype == 'trade_date':
        if os.path.exists(conf_ini):
            config = ConfigObj(conf_ini, encoding='UTF8')

            if classtype in list(config.keys()):
                if xtype in list(config[classtype].keys()):
                    save_date =  config[classtype]['date']
                else:
                    save_date = None
            else:
                save_date = None
                
            if save_date is not None:
                if save_date != get_today() or update:
                    trade_status= is_trade_date()
                    if trade_status is not None or trade_status != 'None':
                        if 'rewrite' in list(config[classtype].keys()):
                            rewrite = int(config[classtype]['rewrite']) + 1
                        else:
                            rewrite = 1
                        config[classtype] = {}
                        config[classtype][xtype] = trade_status
                        config[classtype]['date'] = get_today()
                        config[classtype]['rewrite'] = rewrite
                        config.write()
            else:
                config[classtype] = {}
                config[classtype][xtype] = is_trade_date()
                config[classtype]['date'] = get_today()
                config[classtype]['rewrite'] = 1
                config.write()
        else:
            config = ConfigObj(conf_ini, encoding='UTF8')
            config[classtype] = {}
            config[classtype][xtype] = is_trade_date()
            config[classtype]['date'] = get_today()
            config[classtype]['rewrite'] = 1
                # time.strftime("%H:%M:%S",time.localtime(now))
            config.write()

        return config[classtype][xtype]    

    else:

        currvalue = int(currvalue)
        if os.path.exists(conf_ini):
            config = ConfigObj(conf_ini, encoding='UTF8')

            if not classtype in list(config.keys()):
                if not readonly:
                    config[classtype] = {}
                    config[classtype][xtype] = currvalue
                    config.write()


            elif readonly:
                if xtype in config[classtype].keys() and xtype == 'time':
                    save_value = int(config[classtype][xtype])
                else:
                    save_value = int(currvalue)
                    config[classtype][xtype] = save_value
                    config.write()
                if int_time:
                    return int(time.strftime("%H:%M:%S",time.localtime(save_value))[:6].replace(':',''))
                else:
                    return int(save_value)

            elif not update:
                if classtype in list(config.keys()):
                    if not xtype in list(config[classtype].keys()):
                        config[classtype][xtype] = currvalue
                        config.write()
                        if xtype == 'time':
                            return 1
                    else:
                        if xtype == 'time' and currvalue != 0:
                            time_dif = currvalue - float(config[classtype][xtype])
                        else:
                            time_dif = int(config[classtype][xtype])
                        if int_time:
                            return int(time.strftime("%H:%M:%S",time.localtime(time_dif))[:6].replace(':',''))
                        else:
                            return time_dif

                else:
                    config[classtype] = {}
                    config[classtype][xtype] = 0
                    config.write()
            elif not xtype in config[classtype].keys():
                if update:
                    config[classtype][xtype] = currvalue
                    if xtype == 'time':
                        config[classtype]['otime'] = time.strftime("%H:%M:%S",time.localtime(currvalue))
                    config.write()

            else:
                if xtype == 'time':
                    save_value = float(config[classtype][xtype])
                else:
                    save_value = int(config[classtype][xtype])
                if save_value != currvalue:
                    config[classtype][xtype] = currvalue
                    if xtype == 'time':
                        config[classtype]['otime'] = time.strftime("%H:%M:%S",time.localtime(currvalue))
                    config.write()
        else:
            config = ConfigObj(conf_ini, encoding='UTF8')
            config[classtype] = {}
            config[classtype][xtype] = currvalue
            if xtype == 'time':
                config[classtype]['otime'] = currvalue
                # time.strftime("%H:%M:%S",time.localtime(now))
            config.write()
        return int(currvalue)


def get_config_value_wencai(fname, classtype, currvalue=0, xtype='limit', update=False):
    conf_ini = fname
    # print fname
    currvalue = int(currvalue)
    if os.path.exists(conf_ini):
        config = ConfigObj(conf_ini, encoding='UTF8')
        if not update:
            if classtype in list(config.keys()):
                if not xtype in list(config[classtype].keys()):
                    config[classtype][xtype] = currvalue
                    config.write()
                    if xtype == 'time':
                        return 1
                else:
                    if xtype == 'time' and currvalue != 0:
                        time_dif = currvalue - float(config[classtype][xtype])
                    else:
                        time_dif = int(config[classtype][xtype])
                    return time_dif

            else:
                config[classtype] = {}
                config[classtype][xtype] = 0
                config.write()
        else:
            if xtype == 'time':
                save_value = float(config[classtype][xtype])
            else:
                save_value = int(config[classtype][xtype])
            if save_value != currvalue:
                config[classtype][xtype] = currvalue
                config.write()
    else:
        config = ConfigObj(conf_ini, encoding='UTF8')
        config[classtype] = {}
        config[classtype][xtype] = currvalue
        config.write()
    return int(currvalue)


def get_trade_date_status():
    trade_date = GlobalValues().getkey('trade_date')
    trade_status = GlobalValues().getkey('is_trade_date')
    if  trade_status is None:
        trade_status = get_config_value_ramfile(fname='is_trade_date',currvalue=is_trade_date(),xtype='trade_date')
        if trade_status is None or trade_status == 'None':
            trade_status = get_config_value_ramfile(fname='is_trade_date',currvalue=is_trade_date(),xtype='trade_date',update=True)
        GlobalValues().setkey('is_trade_date',trade_status)
        GlobalValues().setkey('trade_date',get_today())
    if trade_date is not None:
        if trade_date != get_today():
            trade_status = get_config_value_ramfile(fname='is_trade_date',currvalue=is_trade_date(),xtype='trade_date')
            GlobalValues().setkey('is_trade_date',trade_status)
            GlobalValues().setkey('trade_date',get_today())
    
    # lag error: trade_status = get_config_value_ramfile(fname='is_trade_date',currvalue=is_trade_date(),xtype='trade_date')

    return trade_status
# wencai_count = cct.get_config_value_wencai(config_ini,fname,1,update=True)


def get_index_fibl(default=1):
    # import sys
    # sys.path.append("..")
    # from JSONData import powerCompute as pct
    # df = pct.powerCompute_df(['999999','399006','399001'], days=0, dtype='d', end=None, dl=10, talib=True, filter='y',index=True)
    # df = tdd.get_tdx_exp_all_LastDF_DL(
    #             ['999999','399006','399001'], dt=10)

    # if len(df) >0 and 'fibl' in df.columns:
    #     # fibl = int(df.fibl.max())
    #     # fibl = int(df.cumin.max())
    #     fibl = int(df.fibl.max())
    #     fibl = fibl if 4 > fibl > 1 else default
    #     # fibl = fibl if 3 >= fibl >= 1 else 1
    #     # return abs(fibl)
    # else:
    #     fibl = 1
    # # cct.GlobalValues()
    # GlobalValues().setkey('cuminfibl', fibl)
    # GlobalValues().setkey('indexfibl', int(df.fibl.min()))
    # return abs(fibl)
    return default

from collections import Counter,OrderedDict
def counterCategory(df,col='category',table=False,limit=30):
    topSort = []
    if len(df) > 0:
        categoryl = df[col][:limit].tolist()
        dicSort = []
        for i in categoryl:
            if isinstance(i, str):
                if col == 'category':
                    dicSort.extend(i.split(';'))
                else:
                    dicSort.extend(i.split('+'))
                # dicSort.extend([ 'u%s'%(co) for co in i.split(';')])
                
        topSort = Counter(dicSort)
        if not table:
            top5 = OrderedDict(topSort.most_common(5))
            for i in list(top5.keys()):
                if len(i) > 2:
                    print(f'{i}:{top5[i]}', end=' ')
            print('')
        else:
            table_row=f''
            top5 = OrderedDict(topSort.most_common(5))
            for i in list(top5.keys()):
                if len(i) > 2:
                    table_row +=f'{i}:{top5[i]} '
            table_row +='\n'
            topSort = table_row 
    return topSort

# def write_to_dfcfnew(p_name=dfcf_path):
#     pass
def write_to_blkdfcf(codel,conf_ini=dfcf_path,blk='inboll1',append=True):
    import configparser
    if not isMac():
        if not os.path.exists(conf_ini):
            log.error('file is not exists:%s'%(conf_ini))
        else:
            cf = configparser.ConfigParser()  # 实例化 ConfigParser 对象
            # cf.read("test.ini")
            cf.read(conf_ini,encoding='UTF-16')
            # cf.read(conf_ini,encoding='GB2312')
            # return all section
            secs = cf.sections()
            # print('sections:', secs, type(secs))

            opts = cf.options("\\SelfSelect")  # 获取db section下的 options，返回list
            # print('options:', opts, type(opts))
            # 获取db section 下的所有键值对，返回list 如下，每个list元素为键值对元组
            kvs = cf.items("\\SelfSelect")
            # print('db:', dict(kvs).keys())
            # read by type
            truer = cf.get("\\SelfSelect", blk)
            # print('truer:',truer)
            truer_n = truer
            idx = 0

            if isinstance(codel, list):
                for co in codel:
                    if code_to_symbol_dfcf(co) not in truer:
                        idx+=1
                        # print(idx)
                        truer_n = code_to_symbol_dfcf(co)+','+truer_n
                    # else:
                    #     print("no change co")
                        # truer_n = truer
            else:
                if code_to_symbol_dfcf(codel) not in truer:
                        idx+=1
                        truer_n = code_to_symbol_dfcf(codel)+','+truer
                # else:
                #     print("no change co")
                        # truer_n = truer
                        
            print("%s add:%s"%(blk,idx))
            cf.set("\\SelfSelect", blk, truer_n)
            # print('instock:',cf.get("\\SelfSelect", "instock"))
            cf.write(open(conf_ini,"w",encoding='UTF-16'))

def read_unicode_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        contents = file.readlines()
        return contents

def write_unicode_file(file_path, contents):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.writelines(contents)        

def write_evalcmd2file(file_path,content):
    content = content.strip()
    if not os.path.exists(file_path):
        write_unicode_file(file_path,content+'\n')
        # with open("history_data.json", "w+", encoding="utf-8") as f:
        #     f.write("[]")
    else:
        contents=read_unicode_file(file_path)
        if len(content) > 0 and content+'\n' not in contents:
            contents.append(content+'\n')
        write_unicode_file(file_path, contents)
    return True

def write_to_blocknew(p_name, data, append=True, doubleFile=False, keep_last=None,dfcf=False,reappend=True):
    # fname=p_name
    # writename=r'D:\MacTools\WinTools\zd_dxzq\T0002'
    write_to_blocknew_2025(p_name, data, append=append, doubleFile=doubleFile, keep_last=keep_last,dfcf=dfcf,reappend=reappend)
    if not isMac():
        blocknew_path=get_tdx_dir_blocknew_dxzq(p_name)
        write_to_blocknew_2025(blocknew_path, data, append=append, doubleFile=doubleFile, keep_last=keep_last,dfcf=dfcf,reappend=reappend)   
    else:
        # blocknew_path=p_name.replace('new_tdx','new_tdx2')
        blocknew_path=p_name.replace('new_tdx2','new_tdx')
        write_to_blocknew_2025(blocknew_path, data, append=append, doubleFile=doubleFile, keep_last=keep_last,dfcf=dfcf,reappend=reappend)   

def write_to_blocknew_2025(p_name, data, append=True, doubleFile=False, keep_last=None,dfcf=False,reappend=True):
    if keep_last is None:
        keep_last = ct.keep_lastnum
    # index_list = ['1999999','47#IFL0',  '0159915', '27#HSI']
    index_list = ['1999999', '0399001', '0159915','2899050','1588000','1880884','1880885','1880818','1880774']
    # index_list = ['1999999', '0399001', '0159915','2899050','1588000','1880884','1880885','1880818','1880774']
    # index_list = ['1999999','47#IFL0', '0399001', '0159915']
    # index_list = ['1999999','47#IFL0', '27#HSI',  '0399006']
    # index_list = ['1999999','0399001','47#IFL0', '27#HSI',  '0159915']
    # index_list = ['0399001', '1999999', '0159915']
    # index_list = ['1999999', '27#HSI',  '0159915']

    def writeBlocknew(p_name, data, append=True,keep_last=keep_last,reappend=True):
        flist=[]
        if append:
            fout = open(p_name, 'rb+')
            # fout = open(p_name)
            flist_t = fout.readlines()
            # flist_t = file(p_name, mode='rb+', buffering=None)
            # flist = []
            # errstatus=False
            

            for code in flist_t:
                if isinstance(code,bytes):
                    code = code.decode()
                if len(code) <= 6 or len(code) > 12:
                    continue
                if not code.endswith('\r\n'):
                    if len(code) <= 6:
                        # errstatus = True
                        continue
                    else:
                        # errstatus = True
                        code = code + '\r\n'
                flist.append(code)
            for co in index_list:
                inx = (co) + '\r\n'
                if inx not in flist:
                    flist.insert(index_list.index(co), inx)
            # if errstatus:
            # fout.close()
            # fout = open(p_name, 'wb+')
            # for code in flist:
            #     fout.write(code)

            # if not str(flist[-1]).endswith('\r\n'):
                # print "File:%s end not %s"%(p_name[-7:],str(flist[-1]))
            # print "flist", flist
        else:
            if int(keep_last) > 0:
                fout = open(p_name, 'rb+')
                flist_t = fout.readlines()
            else:
                flist_t = []
            # flist_t = file(p_name, mode='rb+', buffering=None)
            if len(flist_t) > 4:
                # errstatus=False
                for code in flist_t:
                    if isinstance(code,bytes):
                        code = code.decode()
                    if not code.endswith('\r\n'):
                        if len(code) <= 6:
                            # errstatus = True
                            continue
                        else:
                            # errstatus = True
                            code = code + '\r\n'
                    flist.append(code)
                # if errstatus:
                if int(keep_last) > 0:
                    fout.close()
                # if p_name.find('066.blk') > 0:
                #     writecount = ct.writeblockbakNum
                # else:
                #     writecount = 9

                writecount = keep_last
                flist = flist[:writecount]

                for co in index_list:
                    inx = (co) + '\r\n'
                    if inx not in flist:
                        flist.insert(index_list.index(co), inx)
                # print flist
                # fout = open(p_name, 'wb+')
                # for code in flist:
                #     fout.write(code)
            else:
                # fout = open(p_name, 'wb+')
                # index_list.reverse()
                for i in index_list:
                    raw = (i) + '\r\n'
                    flist.append(raw)

        counts = 0
        idx = 0
        for i in data:
            # print type(i)
            # if append and len(flist) > 0:
            #     raw = code_to_tdxblk(i).strip() + '\r\n'
            #     if len(raw) > 8 and not raw in flist:
            #         fout.write(raw)
            # else:
            raw = code_to_tdxblk(i) + '\r\n'
            if len(raw) > 8:
                if not raw in flist:
                    if idx == 0 and counts == 0:
                        idx +=1
                        raw2 = code_to_tdxblk('562530') + '\r\n'
                        if not raw2 in flist:
                            flist.append(raw2)
                        else:
                            flist.remove(raw2)
                            flist.append(raw2)
                    counts += 1
                    flist.append(raw)
                else:
                    #if exist will remove and append
                    if reappend:
                        if idx == 0:
                            idx +=1
                            raw2 = code_to_tdxblk('562530') + '\r\n'
                            if not raw2 in flist:
                                flist.append(raw2)
                            else:
                                flist.remove(raw2)
                                flist.append(raw2)

                        flist.remove(raw)
                        flist.append(raw)

        fout = open(p_name, 'wb+')
        for code in flist:
            if not isinstance(code,bytes):
                code = code.encode()
            fout.write(code)
                # raw = pack('IfffffII', t, i[2], i[3], i[4], i[5], i[6], i[7], i[8])
        fout.flush()
        fout.close()
        # if p_name.find('066.blk') >= 0:
        if counts == 0:
            if len(data) == 0:
                log.error("counts and data is None:%s"%(p_name))
            else:
                print(("counts:0 data:%s :%s"%(len(data),p_name)))
        else:
            print("all write to %s:%s" % (p_name, counts))

    blockNew = get_tdx_dir_blocknew() + 'zxg.blk'
    blockNewStart = get_tdx_dir_blocknew() + '077.blk'
    # writeBlocknew(blockNew, data)
    p_data = ['zxg', '069', '068', '067', '061']
    if len(p_name) < 5:
        if p_name in p_data:
            p_name = get_tdx_dir_blocknew() + p_name + '.blk'
            print("p_name:%s" % (p_name))
        else:
            print('p_name is not ok')
            return None

    if p_name.find('061.blk') > 0 or p_name.find('062.blk') > 0 or p_name.find('063.blk') > 0:
        writeBlocknew(p_name, data, append)
        if doubleFile:
            writeBlocknew(blockNew, data, append=True,reappend=reappend)
            # writeBlocknew(blockNewStart, data, append=True)
        # print "write to :%s:%s"%(p_name,len(data))
    elif p_name.find('064.blk') > 0:
        writeBlocknew(p_name, data, append,reappend=reappend)
        if doubleFile:
            writeBlocknew(blockNew, data, append=True,keep_last=9,reappend=reappend)
            # writeBlocknew(blockNewStart, data, append=True)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))
    elif p_name.find('068.blk') > 0 or p_name.find('069.blk') > 0:

        writeBlocknew(p_name, data, append,reappend=reappend)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))

    else:
        writeBlocknew(p_name, data, append,reappend=reappend)
        if doubleFile:
            writeBlocknew(blockNew, data,append=True,reappend=reappend)
            # writeBlocknew(blockNewStart, data, append=True)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))
    if dfcf:
        write_to_blkdfcf(data)

def write_to_blocknewOld(p_name, data, append=True, doubleFile=True, keep_last=None):
    if keep_last is None:
        keep_last = ct.keep_lastnum
    # index_list = ['1999999','47#IFL0',  '0159915', '27#HSI']
    index_list = ['1999999', '0399001', '0159915']
    # index_list = ['1999999','47#IFL0', '0399001', '0159915']
    # index_list = ['1999999','47#IFL0', '27#HSI',  '0399006']
    # index_list = ['1999999','0399001','47#IFL0', '27#HSI',  '0159915']
    # index_list = ['0399001', '1999999', '0159915']
    # index_list = ['1999999', '27#HSI',  '0159915']

    def writeBlocknew__(p_name, data, append=True,keep_last=keep_last):
        if append:
            fout = open(p_name, 'rb+')
            # fout = open(p_name)
            flist_t = fout.readlines()
            # flist_t = file(p_name, mode='rb+', buffering=None)
            flist = []
            # errstatus=False
            for code in flist_t:
                if isinstance(code,bytes):
                    code = code.decode()
                if len(code) <= 6 or len(code) > 12:
                    continue
                if not code.endswith('\r\n'):
                    if len(code) <= 6:
                        # errstatus = True
                        continue
                    else:
                        # errstatus = True
                        code = code + '\r\n'
                flist.append(code)
            for co in index_list:
                inx = (co) + '\r\n'
                if inx not in flist:
                    flist.insert(index_list.index(co), inx)
            # if errstatus:
            fout.close()
            fout = open(p_name, 'wb+')
            for code in flist:
                if not isinstance(code,bytes):
                    code = code.encode()
                fout.write(code)

            # if not str(flist[-1]).endswith('\r\n'):
                # print "File:%s end not %s"%(p_name[-7:],str(flist[-1]))
            # print "flist", flist
        else:
            if int(keep_last) > 0:
                fout = open(p_name, 'rb+')
                flist_t = fout.readlines()
                flist = []
            else:
                flist_t = []
                flist = []
            # flist_t = file(p_name, mode='rb+', buffering=None)
            if len(flist_t) > 4:
                # errstatus=False
                for code in flist_t:
                    if isinstance(code,bytes):
                        code = code.decode()
                    if not code.endswith('\r\n'):
                        if len(code) <= 6:
                            # errstatus = True
                            continue
                        else:
                            # errstatus = True
                            code = code + '\r\n'
                    flist.append(code)
                # if errstatus:
                if int(keep_last) > 0:
                    fout.close()
                # if p_name.find('066.blk') > 0:
                #     writecount = ct.writeblockbakNum
                # else:
                #     writecount = 9

                writecount = keep_last
                flist = flist[:writecount]

                for co in index_list:
                    inx = (co) + '\r\n'
                    if inx not in flist:
                        flist.insert(index_list.index(co), inx)
                # print flist
                fout = open(p_name, 'wb+')
                for code in flist:
                    if not isinstance(code,bytes):
                        code = code.encode()
                    fout.write(code)
            else:
                fout = open(p_name, 'wb+')
                # index_list.reverse()
                for i in index_list:
                    raw = (i) + '\r\n'
                    if not isinstance(raw,bytes):
                        raw = raw.encode()
                    fout.write(raw)

        counts = 0
        for i in data:
            # print type(i)
            # if append and len(flist) > 0:
            #     raw = code_to_tdxblk(i).strip() + '\r\n'
            #     if len(raw) > 8 and not raw in flist:
            #         fout.write(raw)
            # else:
            raw = code_to_tdxblk(i) + '\r\n'
            if len(raw) > 8 and not raw in flist:
                counts += 1
                if not isinstance(raw,bytes):
                    raw = raw.encode()
                fout.write(raw)
                # raw = pack('IfffffII', t, i[2], i[3], i[4], i[5], i[6], i[7], i[8])
        fout.flush()
        fout.close()
        # if p_name.find('066.blk') >= 0:
        if counts == 0:
            if len(data) == 0:
                log.error("counts and data is None:%s"%(p_name))
            else:
                print(("counts:0 data:%s :%s"%(len(data),p_name)))
        else:
            print("all write to %s:%s" % (p_name, counts))

    blockNew = get_tdx_dir_blocknew() + 'zxg.blk'
    blockNewStart = get_tdx_dir_blocknew() + '077.blk'
    # writeBlocknew(blockNew, data)
    p_data = ['zxg', '069', '068', '067', '061']
    if len(p_name) < 5:
        if p_name in p_data:
            p_name = get_tdx_dir_blocknew() + p_name + '.blk'
            print("p_name:%s" % (p_name))
        else:
            print('p_name is not ok')
            return None

    if p_name.find('061.blk') > 0 or p_name.find('062.blk') > 0 or p_name.find('063.blk') > 0:
        writeBlocknew(p_name, data, append)
        if doubleFile:
            writeBlocknew(blockNew, data)
            writeBlocknew(blockNewStart, data, append)
        # print "write to :%s:%s"%(p_name,len(data))
    elif p_name.find('064.blk') > 0:
        writeBlocknew(p_name, data, append)
        if doubleFile:
            writeBlocknew(blockNew, data, append,keep_last=12)
            writeBlocknew(blockNewStart, data, append)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))
    elif p_name.find('068.blk') > 0 or p_name.find('069.blk') > 0:

        writeBlocknew(p_name, data, append)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))

    else:
        writeBlocknew(p_name, data, append)
        if doubleFile:
            writeBlocknew(blockNew, data)
            # writeBlocknew(blockNewStart, data[:ct.writeCount - 1])
            writeBlocknew(blockNewStart, data, append)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))

def reduce_memory_usage(df, verbose=False):
    numerics = ["int8", "int16", "int32", "int64", "float16", "float32", "float64"]
    if df is not None:
        start_mem = df.memory_usage().sum() / 1024 ** 2
        for col in df.columns:
            col_type = df[col].dtypes
            if isinstance(df.index, pd.MultiIndex) and col in ['volume','vol'] and col_type in numerics and str(col_type)[:3] == "int":
                df[col] = df[col].astype(np.int64)
            elif col_type in numerics:
                c_min = df[col].min()
                c_max = df[col].max()
                if str(col_type)[:3] == "int":
                    if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                        df[col] = df[col].astype(np.int8)
                    elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                        df[col] = df[col].astype(np.int16)
                    elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                        df[col] = df[col].astype(np.int32)
                    elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                        df[col] = df[col].astype(np.int64)
                else:
                    if (
                        c_min > np.finfo(np.float16).min
                        and c_max < np.finfo(np.float16).max
                    ):
                        df[col] = df[col].astype(np.float16)
                        df[col] = df[col].apply(lambda x:round(x,2))
                    elif (
                        c_min > np.finfo(np.float32).min
                        and c_max < np.finfo(np.float32).max
                    ):
                        df[col] = df[col].astype(np.float32)
                        df[col] = df[col].apply(lambda x:round(x,2))

                    else:
                        df[col] = df[col].astype(np.float64)
                        df[col] = df[col].apply(lambda x:round(x,2))
                        
        end_mem = df.memory_usage().sum() / 1024 ** 2
        if verbose:
            print(
                "Mem. usage decreased to {:.2f} Mb ({:.1f}% reduction)".format(
                    end_mem, 100 * (start_mem - end_mem) / start_mem
                )
            )
        else:
            log.debug(
                "Mem. usage decreased to {:.2f} Mb ({:.1f}% reduction)".format(
                    end_mem, 100 * (start_mem - end_mem) / start_mem
                )
            )
    return df

# def read_to_indb(days=20,duplicated=False):
#     df = inDb.selectlastDays(days)

#     if not duplicated :
#         df['couts']=df.groupby(['code'])['code'].transform('count')
#         df=df.sort_values(by='couts',ascending=0)
#         df=df.drop_duplicates('code')

#     return (df)

def read_to_blocknew(p_name):
    index_list = ['1999999', '0399001', '47#IFL0', '27#HSI',  '0159915']

    def read_block(p_name):
        fout = open(p_name, 'rb')
        # fout = open(p_name)
        flist_t = fout.readlines()
        flist = []
        for code in flist_t:
            if isinstance(code,bytes):
                code = code.decode()
            if len(code) <= 6 or len(code) > 12:
                continue
            if code.endswith('\r\n'):
                if len(code) <= 6 or code in index_list:
                    # errstatus = True
                    continue
                else:
                    code = code.replace('\r\n', '')
                    if code not in index_list:
                        code = tdxblk_to_code(code)
            else:
                continue
            if len(code) == 6 and code not in index_list:
                flist.append(code)
        fout.close()
        return flist

    if not p_name.endswith("blk"):
        blockNew = get_tdx_dir_blocknew() + p_name + '.blk'
        if not os.path.exists(blockNew):
            log.error("path error:%s" % (blockNew))
    else:
        blockNew = get_tdx_dir_blocknew() + p_name

    if os.path.exists(blockNew):
        codelist = read_block(blockNew)
    else:
        codelist = []
    # blockNewStart = get_tdx_dir_blocknew() + '066.blk'
    # writeBlocknew(blockNew, data)
    # p_data = ['zxg', '069', '068', '067', '061']
    return codelist


def getFibonacci(num, days=None):
    res = [0, 1]
    a = 0
    b = 1
    for i in range(0, num):
        if i == a + b:
            res.append(i)
            a, b = b, a + b
    if days is None:
        return res
    else:
        fib = days
        for x in res:
            if days <= x:
                fib = x
                break
        return fib

# def getFibonacciCount(num,days):
    # fibl = getFibonacci(num)
    # fib = days
    # for x in fibl:
        # if days < x:
        # fib = x
        # break
    # return fib


# def varname(p):
#     import inspect
#     for line in inspect.getframeinfo(inspect.currentframe().f_back)[3]:
#         m = re.search(r'\bvarname\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)', line)
#         if m:
#             return m.group(1)


# def varnamestr(obj, namespace=globals()):
#     # namestr(a, globals())
#     if isinstance(namespace, dict):
#         n_list = [name for name in namespace if namespace[name] is obj]
#     else:
#         log.error("namespce not dict")
#         return None
#         # n_list = [name for name in namespace if id(name) == id(obj)]

#     for n in n_list:
#         if n.startswith('_'):
#             continue
#         else:
#             return n
#     return None

# multiIndex_func = {'close': 'mean', 'low': 'min', 'high': 'max', 'volume': 'sum', 'open': 'first'}
# multiIndex_func = {'close': 'mean', 'low': 'min', 'high': 'max', 'volume': 'sum', 'open': 'first'}

#20240301
multiIndex_func = {'close': 'mean', 'low': 'min', 'high': 'max', 'volume': 'last', 'open': 'first'}

def using_Grouper_eval(df, freq='5T', col='low', closed='right', label='right'):
    func = {}
    if col == 'all':
        for k in df.columns:
            if k in list(multiIndex_func.keys()):
                if k == 'close':
                    func[k] = 'first'
                else:
                    func[k] = multiIndex_func[k]

    elif isinstance(col, list):
        for k in col:
            if k in list(multiIndex_func.keys()):
                func[k] = multiIndex_func[k]
    else:
        if col in list(multiIndex_func.keys()):
            func[col] = multiIndex_func[col]
    level_values = df.index.get_level_values
    return eval("(df.groupby([level_values(i) for i in [0]]+[pd.Grouper(freq=freq, level=-1,closed='%s',label='%s')]).agg(%s))" % (closed, label, func))


# def using_Grouper(df, freq='5T', col='low', closed='right', label='right'):
def using_Grouper(df, freq='5T', col='low', closed='right', label='right'):
    func = {}
    if col == 'all':
        for k in df.columns:
            if k in list(multiIndex_func.keys()):
                if k == 'close':
                    func[k] = 'last'
                else:
                    func[k] = multiIndex_func[k]

    elif isinstance(col, list):
        for k in col:
            if k in list(multiIndex_func.keys()):
                func[k] = multiIndex_func[k]
    else:
        if col in list(multiIndex_func.keys()):
            func[col] = multiIndex_func[col]
    level_values = df.index.get_level_values
    return (df.groupby([level_values(i) for i in [0]] + [pd.Grouper(freq=freq, level=-1, closed=closed, label=label)]).agg(func))


def select_multiIndex_index(df, index='ticktime', start=None, end=None, datev=None, code=None):
    # df = df[df.index.duplicated()]

    # df = df.drop_duplicates('volume')

    if len(str(df.index.get_level_values(1)[-1])) > 10:
        index_date = str(df.index.get_level_values(1)[-1])[:10]
    else:
        index_date = None
    if index != 'date' and code is None:
        if start is not None and len(start) < 10:
            if datev is None:
                if index_date != None:
                    start = index_date + ' ' + start
                else:
                    start = get_today() + ' ' + start
            else:
                start = day8_to_day10(datev) + ' ' + start
            if end is None:
                end = start
        else:
            if end is None:
                end = start
        if end is not None and len(end) < 10:
            if datev is None:
                if index_date != None:
                    end = index_date + ' ' + end
                else:
                    end = get_today() + ' ' + end
                if start is None:
                    start = get_today(sep='-') + ' ' + '09:25:00'
            else:
                end = day8_to_day10(datev) + ' ' + end
                if start is None:
                    start = day8_to_day10(datev) + ' ' + '09:25:00'
        else:
            if start is None:
                if end is None:
                    if index_date != None:
                        start = index_date + ' ' + '09:25:00'
                        end = index_date + ' ' + '09:45:00'
                        log.error("start and end is None to 930 and 945")
                    else:
                        start = get_today(sep='-') + ' ' + '09:25:00'
                        end = get_today(sep='-') + ' ' + '09:45:00'
                        log.error("start and end is None to 930 and 945")
                else:
                    start = end
    else:
        start = day8_to_day10(start)
        end = day8_to_day10(end)

    if code is not None:
        if start is None:
            if index_date != None:
                start = index_date + ' ' + '09:24:30'
            else:
                start = get_today(sep='-') + ' ' + '09:24:30'
        else:
            start = day8_to_day10(start) + ' ' + '09:24:30'
        # df = df[(df.index.get_level_values('code') == code) & (df.index.get_level_values(index) > start)]
        df = df[(df.index.get_level_values('code') == code)]

    if start is None and end is not None:
        df = df[(df.index.get_level_values(index) <= end)]
    elif start is not None and end is None:
        df = df[(df.index.get_level_values(index) >= start)]
    elif start is not None and end is not None:
        idx = df.index.get_level_values(index)[0] if len(df.index.get_level_values(index)) > 0 else 0
        idx_end = pd.Timestamp(end) if index == 'ticktime' else end
        log.info("idx:%s idx<=end:%s" % (idx, idx <= idx_end))
        if idx <= idx_end:
            df = df[(df.index.get_level_values(index) >= start) & (df.index.get_level_values(index) <= end)]
        else:
            df = df[(df.index.get_level_values(index) >= start)]
    else:
        log.info("start end is None")
    return df


def from_list_to_dict(col, func_dict):
    func = {}
    if isinstance(col, list):
        for k in col:
            if k in list(func_dict.keys()):
                func[k] = func_dict[k]
    elif isinstance(col, dict):
        func = col
    else:
        if col in list(func_dict.keys()):
            func[col] = func_dict[col]
    return func


def get_limit_multiIndex_Row(df, col=None, index='ticktime', start=None, end='10:00:00'):
    """[summary]

    [description]

    Arguments:
        df {[type]} -- [description]

    Keyword Arguments:
        col {[type]} -- [description] (default: {None})
        index {str} -- [description] (default: {'ticktime'})
        start {[type]} -- [description] (default: {None})
        end {str} -- [description] (default: {'10:00:00'})

    Returns:
        [type] -- [description]
    """
    if df is not None:
        df = select_multiIndex_index(df, index=index, start=start, end=end)
    else:
        log.error("df is None")
    if col is not None:
        # import pdb;pdb.set_trace()
        func = from_list_to_dict(col, multiIndex_func)
        df = df.groupby(level=[0]).agg(func)
    else:
        log.info('col is None')
    return df



def get_limit_multiIndex_freq(df, freq='5T', col='low', index='ticktime', start=None, end='10:00:00', code=None):
    # quotes = cct.get_limit_multiIndex_freq(h5, freq=resample.upper(), col='all', start=start, end=end, code=code)
    # isinstance(spp.all_10.index[:1], pd.core.index.MultiIndex)
    if df is not None:
        dd = select_multiIndex_index(df, index=index, start=start, end=end, code=code)
        if code is not None:
            df = dd.copy()
            df['open'] =  dd['close']
            df['high'] =  dd['close']
            df['low'] =  dd['close']
        else:
            df = dd.copy()
    else:
        log.error("df is None")
    # print df.loc['600007',['close','ticktime']]
    if freq is not None and col is not None:
        if col == 'all':
            vol0 = df.volume[0]
            df['volume'] = df.volume - df.volume.shift(1)
            df['volume'][0] = vol0
            # vol0 = df.loc[:, 'volume'][0]
            # df.loc[:,'volume'] = df.volume - df.volume.shift(1)
            # df.loc[:, 'volume'][0] = vol0
        df = using_Grouper(df, freq=freq, col=col)
        # print df.loc['600007',['close','low','high','ticktime']]
    else:
        log.info('freq is None')
    # df = select_multiIndex_index(df, index=index, start=start, end=end)
    # if col == 'close':
        # df.rename(columns={'close': 'low'}, inplace=True)
    return df


def get_stock_tdx_period_to_type(stock_data, type='w'):
    period_type = type
    stock_data.index = pd.to_datetime(stock_data.index)
    period_stock_data = stock_data.resample(period_type).last()
    # 周数据的每日change连续相乘
    # period_stock_data['percent']=stock_data['percent'].resample(period_type,how=lambda x:(x+1.0).prod()-1.0)
    # 周数据open等于第一日
    period_stock_data['open'] = stock_data['open'].resample(period_type).first()
    # 周high等于Max high
    period_stock_data['high'] = stock_data['high'].resample(period_type).max()
    period_stock_data['low'] = stock_data['low'].resample(period_type).min()
    # volume等于所有数据和
    period_stock_data['amount'] = stock_data['amount'].resample(period_type).sum()
    period_stock_data['vol'] = stock_data['vol'].resample(period_type).sum()
    # 计算周线turnover,【traded_market_value】 流通市值【market_value】 总市值【turnover】 换手率，成交量/流通股本
    # period_stock_data['turnover']=period_stock_data['vol']/(period_stock_data['traded_market_value'])/period_stock_data['close']
    # 去除无交易纪录
    period_stock_data = period_stock_data[period_stock_data['code'].notnull()]
    period_stock_data.reset_index(inplace=True)
    return period_stock_data


def MoniterArgmain():

    parser = argparse.ArgumentParser()
    # parser = argparse.ArgumentParser(description='LinearRegression Show')
    parser.add_argument('code', type=str, nargs='?', help='999999')
    parser.add_argument('start', nargs='?', type=str, help='20150612')
    # parser.add_argument('e', nargs='?',action="store", dest="end", type=str, help='end')
    parser.add_argument('end', nargs='?', type=str, help='20160101')
    parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['d', 'w', 'm'], default='d',
                        help='DateType')
    parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['f', 'b'], default='f',
                        help='Price Forward or back')
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low','open','close'], default='close',
    parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low', 'close'], default='close',
                        help='type')
    parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='n',
                        help='find duration low')
    return parser

# def writeArgmainParser(args,defaul_all=30):
#     # from ConfigParser import ConfigParser
#     # import shlex
#     import argparse
#     parser = argparse.ArgumentParser()
#     parser.add_argument('code', type=str, nargs='?', help='w or a or all')
#     parser.add_argument('dl', nargs='?', type=str, help='1,5,10',default=ct.writeCount)
#     parser.add_argument('end', nargs='?', type=str, help='1,5,10',default=None)
#     arg_t = parser.parse_args(args)
#     if arg_t.dl == 'all':
#         # print arg_t.dl
#         arg_t.dl = defaul_all
#     # print arg_t.dl
#     return arg_t

def writeArgmain_block():
    # from ConfigParser import ConfigParser
    # import shlex
    parser = argparse.ArgumentParser()
    parser.add_argument('code', type=str, nargs='?', help='w or a or all')
    parser.add_argument('dl', nargs='?', type=str, help='1,5,10', default=ct.writeCount)
    parser.add_argument('blk', nargs='?', type=str, help='064,065', default=None)
    return parser

def writeArgmain():
    # from ConfigParser import ConfigParser
    # import shlex
    parser = argparse.ArgumentParser()
    parser.add_argument('code', type=str, nargs='?', help='w or a or all')
    parser.add_argument('dl', nargs='?', type=str, help='1,5,10', default=ct.writeCount)
    parser.add_argument('end', nargs='?', type=str, help='1,5,10', default=None)
    # if parser.code == 'all':
    #     print parser.dl
    # parser.add_argument('end', nargs='?', type=str, help='20160101')
    # parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['d', 'w', 'm'], default='d',
    #                     help='DateType')
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['f', 'b'], default='f',
    #                     help='Price Forward or back')
    # parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['high', 'low', 'close'], default='low',
    #                     help='price type')
    # parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='n',
    #                     help='find duration low')
    # parser.add_argument('-l', action="store", dest="dl", type=int, default=None,
    #                     help='dl')
    # parser.add_argument('-dl', action="store", dest="days", type=int, default=1,
    #                     help='days')
    # parser.add_argument('-m', action="store", dest="mpl", type=str, default='y',
    #                     help='mpl show')
    return parser


def DurationArgmain():
    parser = argparse.ArgumentParser()
    # parser = argparse.ArgumentParser(description='LinearRegression Show')
    # parser.add_argument('code', type=str, nargs='?', help='999999')
    parser.add_argument('start', nargs='?', type=str, help='20150612')
    # parser.add_argument('e', nargs='?',action="store", dest="end", type=str, help='end')
    parser.add_argument('end', nargs='?', type=str, help='20160101')
    # parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['d', 'w', 'm'], default='d',
    #                     help='DateType')
    # parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['f', 'b'], default='f',
    #                     help='Price Forward or back')
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low','open','close'], default='close',
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low', 'close'], default='close',
    # help='type')
    parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='n',
                        help='filter low')
    return parser

# def RawMenuArgmain():
#     raw = 'status:[go(g),clear(c),[d 20150101 [l|h]|[y|n|pn|py],quit(q),W(a),sh]:'
#     raw_input_menu=raw+"\n\tNow : %s"+"\n\t1:Sort By Percent\t2:Sort By DFF\t3:Sort By OPRa\t\n\t4:Sort By Ra \t\t5:Sort by Counts\nplease input:"
#     return raw_input_menu


def LineArgmain():
    # from ConfigParser import ConfigParser
    # import shlex
    # parser = argparse.ArgumentParser()
    # parser.add_argument('-s', '--start', type=int, dest='start',
    # help='Start date', required=True)
    # parser.add_argument('-e', '--end', type=int, dest='end',
    # help='End date', required=True)
    # parser.add_argument('-v', '--verbose', action='store_true', dest='verbose',
    # help='Enable debug info')
    # parser.add_argument('foo', type=int, choices=xrange(5, 10))
    # args = parser.parse_args()
    # print args.square**2
    parser = argparse.ArgumentParser()
    # parser = argparse.ArgumentParser(description='LinearRegression Show')
    parser.add_argument('code', type=str, nargs='?', help='999999')
    parser.add_argument('start', nargs='?', type=str, help='20150612')
    # parser.add_argument('e', nargs='?',action="store", dest="end", type=str, help='end')
    parser.add_argument('end', nargs='?', type=str, help='20160101')
    parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['d', 'w', 'm'], default='d',
                        help='DateType')
    parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['f', 'b'], default='f',
                        help='Price Forward or back')
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low','open','close'], default='close',
    parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low', 'close'], default='close',
                        help='type')
    parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='y',
                        help='find duration low')
    # parser.add_argument('-help',type=str,help='Price Forward or back')
    # args = parser.parse_args()
    # args=parser.parse_args(input)
    # parser = parseArgmain()
    # args = parser.parse_args(num_input.split())

    # def getArgs():
    # parse=argparse.ArgumentParser()
    # parse.add_argument('-u',type=str)
    # parse.add_argument('-d',type=str)
    # parse.add_argument('-o',type=str)
    # args=parse.parse_args()
    # return vars(args)
    # if args.verbose:
    # logger.setLevel(logging.DEBUG)
    # else:
    # logger.setLevel(logging.ERROR)
    return parser


# def negate_boolean_list(negate_list, idx=1):
#     cout_all = len(negate_list)
#     if idx < cout_all:
#         sort_negate_l = [key ^ 1 for key in negate_list[:idx]]
#         sort_negate_l.extend(negate_list[idx:])
#     else:
#         sort_negate_l = [key ^ 1 for key in negate_list]

#     return sort_negate_l


def sort_by_value(df, column='dff', file=None, count=5, num=5, asc=0):
    """[summary]

    [description]

    Arguments:
        df {dataframe} -- [description]

    Keyword Arguments:
        column {str} -- [description] (default: 'dff' or ['dff',])
        file {[type]} -- [description] (default: {069})
        count {number} -- [description] (default: {5})
        num {number} -- [description] (default: {5})
        asc {number} -- [description] (default: {1} or [0,1])

    Returns:
        [type] -- [description]
    """
    if not isinstance(column, list):
        dd = df.sort_values(by=[column], ascending=[asc])
    else:
        dd = df.sort_values(by=column, ascending=asc)
    if file is None:
        if num > 0:
            print(dd.iloc[0:num, 0:10])
            print(dd.iloc[0:num, 31:40])
            print(dd.iloc[0:num, -15:-4])
        else:
            print(dd.iloc[num::, 0:10])
            print(dd.iloc[0:num, 31:40])
            print(dd.iloc[num::, -15:-4])
        return dd
    else:
        if str(count) == 'all':
            write_to_blocknew(file, dd.index.tolist(), append=True)
        else:
            write_to_blocknew(file, dd.index.tolist()[:int(count)], append=True)
        print("file:%s" % (file))


def get_col_in_columns(df, idx_value, key):
    """[summary]

    [description]

    Arguments:
        df {[type]} -- [description]
        idx_value {[type]} -- [perc%sd]
        key {[type]} -- [9]

    Returns:
        [type] -- [description]
    """
    idx_k = 1
    # for inx in range(int(key) - 1, 1, -1): stock_filter
    for inx in range(int(key), 1, -1):
        if idx_value % inx in df.columns:
            idx_k = inx
            break
    return idx_k


def get_diff_dratio(mainlist, sublist):
    dif_co = list(set(mainlist) & set(sublist))
    dratio = round((float(len(sublist)) - float(len(dif_co))) / float(len(sublist)), 2)
    log.info("dratio all:%s :%s %0.2f" % (len(sublist), len(sublist) - len(dif_co), dratio))
    return dratio


# def func_compute_percd(c, lp, lc, lh, ll, nh, nl,llp):
def func_compute_percd(close, lastp, op, lasth, lastl, nowh, nowl):
    initc = 0
    down_zero, down_dn, percent_l = 0, 0, 2
    # da, down_zero, down_dn, percent_l = 1, 0, 0, 2
    initc = 1 if (c - lc) / lc * 100 >= 1 else down_dn
    # n_p = (c - lc) / lc * 100
    # n_hp = nh - lh
    # n_lp = nl - ll
    # if n_p >= 0:
    #     if n_p > percent_l and n_hp > 0:
    #         initc += 2
    #     else:
    #         initc += 1
    #     if lp > 0 and n_lp > 0:
    #         initc += 1
    # else:
    #     if n_p < -percent_l and n_hp < 0:
    #         initc -= 2
    #     else:
    #         initc -= 1
    #     if lp < 0 and n_lp < 0:
    #         initc -= 1
    return initc



# import numba as nb
# @numba.jit(nopython=True)
# @nb.autojit
def func_compute_percd2020( open, close,high, low,lastopen, lastclose,lasthigh, lastlow, ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None):
    # down_zero, down_dn, percent_l = 0, 0, 2
     # (1 if ( ((c >= op) and ((c - lc)/lc*100 >= 0)) or (c >= op and c >=m5a) ) else down_dn)
    # df['vol'],df['vol'].shift(1),df['upper']

    initc = 0
    if  0 < lastclose < 1000 and lasthigh != 1.0 and lastlow != 1.0 and lasthigh != 0 and lastlow != 0:
#        close = round(close, 1)
#        lastp = round(lastp, 1)
#        op = round(op, 1)
#        lastopen = round(lastopen, 1)
#        lasth = round(lasth, 1)
#        lastl = round(lastl, 1)
        percent = round((close - lastclose)/lastclose*100,1)
        # now_du = round((high - low)/low*100,1)
        close_du = round((high - low)/low*100,1)
        # last_du = round((lasthigh - lastlow)/lastlow*100,1)
        # volratio = round((nowvol / lastvol),1)
        vol_du = round((nowvol)/lastvol,1)

        if open >= lastclose and close == high and close > ma5:
            initc +=3
            if close > ma5:
                if close < ma5*1.1:
                    initc +=3*vol_du
                elif close < ma5*1.2:
                    initc +=2*vol_du
                else:
                    initc+=2

        elif percent > 2 and low > lastlow and high > lasthigh:
            initc +=2

        elif percent > 2 and close_du > 9 and vol_du > 2:
            initc += 1*vol_du
        elif percent > 2 :
            initc +=1
        elif open > ma5 and open > ma10 :
            initc +=0.1
            if  vol_du < 0.6:
                initc +=0.1
        elif percent < -2 and low < lastlow and high < lasthigh:
            initc -=1
        elif percent < -5:
            initc -=2
        elif close < ma5 and close < ma10:
            initc -=0.51
        # else:
            # initc -=1
    elif  np.isnan(lastclose) :
        if close > open:
            initc +=1


    return initc
def get_col_market_value_df(df,col,market_value):
    if int(market_value) < 10:
        re_str = "%s[1-%s]d$"%(col,market_value)
        temp = df.filter(regex=re_str, axis=1)
        # temp =df.loc[:,df.columns.str.contains( "%s[1-%s]d$"%(col,market_value),regex= True)]
        # temp =df.loc[:,df.columns.str.contains( "%s[1-%s]d$"%(col,market_value),regex= True)]
    else:
        if int(market_value) <= ct.compute_lastdays:
                _remainder = int(market_value)%10
        else:
            _remainder = int(ct.compute_lastdays)%10
        # df.loc[:,df.columns.str.contains( "%s[0-9][0-%s]d$"%(col,_remainder),regex= True)][:1]
        # temp =df.loc[:,df.columns.str.contains( "%s([1-9]|1[0-%s])d$"%(col,_remainder),regex= True)]
        re_str = "%s([1-9]|1[0-%s])d$"%(col,_remainder)
        temp = df.filter(regex=re_str, axis=1)
        # temp =df.loc[:,df.columns.str.contains(re_str,regex= True)]

    return temp

def func_compute_percd2024( open, close,high, low,lastopen, lastclose,lasthigh, lastlow, ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None,high4=None,max5=None,hmax=None,lastdu4=None,code=None):
    initc = 0
    percent_idx = 2
    vol_du_idx = 1.2
    close_du = 0
    vol_du = 0
    top_max_up = 10

    if np.isnan(lastclose):
        percent = round((close - open)/open*100,1)
        lastp = 0
    else:
        percent = round((close - lastclose)/lastclose*100,1)
        lastp = round((lastclose - lastopen)/lastclose*100,1)

    if  low > 0 and  lastclose > 0 and lastvol > 0 and lasthigh > 1.0 and lastlow > 1.0 and lasthigh > 0 and lastlow > 0:
        percent = round((close - lastclose)/lastclose*100,1)
        # now_du = round((high - low)/low*100,1)
        close_du = round((high - low)/low*100,1)
        # last_du = round((lasthigh - lastlow)/lastlow*100,1)
        # volratio = round((nowvol / lastvol),1)
        vol_du = round((nowvol)/lastvol,1)

        # if idate == "2022-11-28":

        if (percent > percent_idx and low > lastlow and (close_du > percent_idx or vol_du > vol_du_idx)) or (high > lasthigh and (low > lastlow and close > ma5) ):
            initc +=1
            # if  close_du > 5:
            #     initc +=0.1
        # elif percent < -percent_idx or (percent < 0 and close_du > 3):
        elif percent < -percent_idx:
            initc -=1
            # if close > open:
            #     #下跌中继,或者止跌信号
            #     initc +=3
            # if  close_du > 5:
            #     initc -=0.1

        # if percent >0 and open >= lastclose and close == high and close > ma5:
        #     initc +=1
        #     if close > ma5:
        #         if close < ma5*1.1:
        #             initc +=3*vol_du
        #         elif close < ma5*1.2:
        #             initc +=2*vol_du
        #         else:
        #             initc+=2

        # elif percent > 3 and low >= lastlow and high > lasthigh:
        #     initc +=2

        # elif percent > 3 and close_du > 9 and vol_du > 2:
        #     initc += 1*vol_du
        # elif percent > 2 :
        #     initc +=1
        # elif percent > 0  and open > ma5 and open > ma10 :
        #     initc +=1
        #     if  vol_du < 0.6:
        #         initc +=0.1
        # elif low < lastlow and high < lasthigh:
        #     initc -=1
        # elif percent < -5 and low < lastlow:
        #     initc -=2
        # elif percent < 0 and close < ma5 and close < ma10:
        #     initc -=0.51
        # else:
            # initc -=1
    elif  np.isnan(lastclose) :
        if close > open:
            initc +=percent
        else:
            initc -=percent

    # open, close,high, low,lastopen, lastclose,lasthigh, lastlow, 
    # ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None

    if  np.isnan(lastclose):
        if percent > 3 and close > ma5 and high > ma10:
            initc +=2
    else:

        if close > lasthigh:
            initc +=0.1
            # if  ma5 > ma10:
            #     initc +=0.1
            # else:
            #     initc -=0.11
        elif close < lastlow:
            initc -=0.1

        if low > lastlow:
            initc +=0.1
            if high >lasthigh:
                initc +=0.1
                
        if high > lasthigh and close > lasthigh and percent > 3 and ma5 > ma10:

            if lastp < -2:
                initc +=12
            else:
                initc +=2
            if (open >= low or (open >lastclose and close > lasthigh)) and close >= high*0.92:
                initc +=2
                if lastclose >= lasthigh*0.98 or lastclose > (lasthigh + lastlow)/2:
                    initc +=2
                    if close_du > 5 and vol_du > 0.8 and vol_du < 2.2:
                        initc +=5
            elif low > lasthigh:
                initc +=2
            elif close == high:
                initc +=1

            if hmax is not None and high >= hmax:
                # if idate == '300093':
                #     import ipdb;ipdb.set_trace()

                if high4 is not None and max5 is not None:
                    if hmax > high4 and high4 > max5:
                        initc +=10
                else:
                    initc +=3

            if high4 is not None and (high >= high4 or (get_work_time_duration() and high >high4)):

                if lastdu4 is not None:
                    if lastdu4 <= 1.12:
                        initc +=3
                    elif lastdu4 > 1.12 and lastdu4 <= 1.21:
                        initc +=2
                    elif lastdu4 > 1.21 and lastdu4 <= 1.31:
                        initc +=2
                    elif lastdu4 > 1.31 and lastdu4 <= 1.5:
                        initc +=2
                    else:
                        initc +=1

                if max5 is not None and high >= max5:
                    initc +=2
                    # if hmax is not None and close > hmax:
                    #     initc +=3
                    #     lastMax = max(high4,max5,hmax)
                    #     if close >= lastMax and lastclose < lastMax or (not get_work_time_duration() and high >=lastMax):
                    #         if lastdu4 is not None:
                    #             if lastdu4 <= 1.05:
                    #                 initc +=10
                    #             elif lastdu4 > 1.05 and lastdu4 <= 1.1:
                    #                 initc +=8
                    #             elif lastdu4 > 1.1 and lastdu4 <= 1.2:
                    #                 initc +=5
                    #             elif lastdu4 > 1.2 and lastdu4 <= 1.3:
                    #                 initc +=3
                    #             else:
                    #                 initc +=2
                    #         else:
                    #             initc +=1
                    #     else:
                    #         initc +=3
                    #     if close == high:
                    #         initc +=2
                    #     elif close >=high*0.99:
                    #         initc +=2

            # if (lastclose <= upper and high >= upper) | ( ((lastclose >= upper) | (lastp >= 5))):
            if (lastclose <= upper and high >= upper) | ( ((lastclose >= upper) | (lastp >= 5))):
                initc +=percent
                if high4 is not None and hmax is not None:
                    lastMax = max(high4,max5,hmax)
                    if lasthigh >= lastMax:
                        # initc += 5 + abs(lastp)
                        initc += 2 + abs(lastp)
                    if lastMax==hmax and high4 > max5 and high4 < hmax:
                        initc += 1

    if GlobalValues().getkey('percdf') is not None:
        # if code == '601857':
        #     import ipdb;ipdb.set_trace()
        if code in GlobalValues().getkey('percdf').index:
            lastdf = GlobalValues().getkey('percdf').loc[code]
            if percent > 2:
                if lastdf.lasth1d < lastdf.lasth2d < lastdf.lasth3d:
                    if close > lastdf.lasth1d:
                        initc += 3
                        if lastdf.lasth3d < lastdf.lasth4d:
                            initc += 2
                            
                            if lastdf.lasth4d < lastdf.lasth5d:
                                initc += 2
                                if lastdf.lasth5d < lastdf.lasth6d:
                                    initc += 2
                    if low < lastdf.ma51d and high > lastdf.ma51d:
                        initc += 3
                elif lastdf.lasth2d < lastdf.lasth3d < lastdf.lasth4d:
                    if close > lastdf.lasth1d > lastdf.lasth2d:
                        initc += 2
                        if lastdf.lasth3d < lastdf.lasth4d:
                            initc += 2
                            if lastdf.lasth4d < lastdf.lasth5d:
                                initc += 2
                                if lastdf.lasth5d < lastdf.lasth6d:
                                    initc += 2
                    if low < lastdf.ma51d and high > lastdf.ma51d:
                        initc += 2
                                     
                elif lastdf.lasth1d > lastdf.lasth2d > lastdf.lasth3d and lastdf.ma51d < lastdf.lastl1d < lastdf.ma51d*1.02 :
                    initc += 3
                    if lastdf.ma51d < lastdf.lastl1d < lastdf.ma51d*1.02:
                        initc += 2

        # else:
        #     log.info("check lowest in percdf:%s"%(code))
            # print("lowest:%s"%(code),end=' ')

    return round(initc,1)



def func_compute_percd2021_vectorized(dd):
    """
    向量化计算股票综合评分，逻辑对应 func_compute_percd2021
    假设 df 中包含以下列：
    ['open', 'close', 'high', 'low', 'last_open', 'last_close', 'last_high', 'last_low',
     'ma5d', 'ma10d', 'vol', 'last_vol', 'upper', 'high4', 'max5', 'hmax', 'lastdu4', 'code']
    """

    df = dd.copy()
    df['last_open']  = df['open'].shift(1)
    df['last_close'] = df['close'].shift(1)
    df['last_high']  = df['high'].shift(1)
    df['last_low']   = df['low'].shift(1)
    df['last_vol']   = df['vol'].shift(1)
    score = pd.Series(0.0, index=df.index)

    # 基础数据
    percent_change = (df['close'] - df['last_close']) / df['last_close'] * 100
    vol_ratio = df['vol'] / df['last_vol']
    valid_mask = (~df['last_close'].isna()) & (df['last_close'] != 0) & (~df['last_vol'].isna()) & (df['last_vol'] != 0)
    score.loc[~valid_mask] = 0.0

    # ====================
    # 1️⃣ 刚启动强势股（安全拉升）
    # ====================
    mask_outer = valid_mask & (df['high'] > df['high4']) & (percent_change > 5) & (df['last_close'] < df['high4'])
    mask_inner = mask_outer & (df['high'] >= df['open']) & (df['open'] > df['last_close']) & \
                 (df['close'] > df['last_close']) & (df['close'] >= df['high']*0.99) & \
                 ((df['high'] < df['hmax']) | (df['last_high'] < df['hmax']))

    # 市场前缀加分
    for prefix, high_score, low_score in [('6',25,20), ('0',25,20), ('3',35,20), ('688',35,18), ('8',35,18)]:
        mask = mask_inner & df['code'].astype(str).str.startswith(prefix)
        score.loc[mask & (percent_change >= 5)] += high_score
        score.loc[mask & (percent_change < 5)] += low_score

    mask_other = mask_inner & ~(df['code'].astype(str).str.startswith(('6','0','3','688','8')))
    score.loc[mask_other] += 15.0

    # 外层非高开高走安全启动加分
    score.loc[mask_outer] += 15.0

    # ====================
    # 2️⃣ 收盘价突破与高点
    # ====================
    score.loc[valid_mask & (df['close'] > df['last_close'])] += 1.0
    score.loc[valid_mask & (df['high'] > df['last_high'])] += 1.0
    score.loc[valid_mask & (df['close'] >= df['high']*0.998)] += 5.0
    score.loc[valid_mask & (vol_ratio > 2) & (df['close'] >= df['high']*0.998)] += 5.0
    score.loc[valid_mask & (df['low'] > df['last_low'])] += 1.0
    score.loc[valid_mask & (df['last_close'] <= df['upper']) & (df['close'] > df['upper'])] += 10.0
    score.loc[valid_mask & (df['open'] > df['last_high']) & (df['close'] > df['open']) &
              (df['last_close'] <= df['upper']) & (df['close'] > df['upper'])] += 10.0
    score.loc[valid_mask & (df['close'] >= df['upper'])] += 5.0
    score.loc[valid_mask & (1.0 < vol_ratio) & (vol_ratio < 2.0)] += 2.0
    score.loc[valid_mask & (df['high'] > df['high4'])] += 3.0
    score.loc[valid_mask & (percent_change > 3) & (df['close'] >= df['high']*0.95) &
              (df['high'] > df['max5']) & (df['high'] > df['high4'])] += 5.0
    score.loc[valid_mask & (df['hmax'].notna()) & (df['high'] >= df['hmax'])] += 20.0
    score.loc[valid_mask & (df['low'] > df['last_high'])] += 20.0
    score.loc[valid_mask & (df['low'] > df['last_high']) & (df['close'] > df['open'])] += 5.0

    # ====================
    # 低开高走 & 放量 & MA5
    # ====================
    mask_low_open = valid_mask & (df['open'] == df['low'])
    score.loc[mask_low_open & (df['open'] < df['last_close']) & (df['open'] >= df['ma5d']) & (df['close'] > df['open'])] += 15.0
    score.loc[mask_low_open & (df['close'] > df['open'])] += 8.0
    score.loc[mask_low_open & (vol_ratio > 2)] += 5.0
    score.loc[valid_mask & (percent_change > 5)] += 8.0

    # ====================
    # 3️⃣ 减分项
    # ====================
    score.loc[valid_mask & (df['close'] < df['last_close'])] -= 1.0
    score.loc[valid_mask & (df['low'] < df['last_low'])] -= 3.0
    score.loc[valid_mask & (df['close'] < df['last_close']) & (df['vol'] > df['last_vol'])] -= 8.0
    score.loc[valid_mask & (df['last_close'] >= df['ma5d']) & (df['close'] < df['ma5d'])] -= 5.0
    score.loc[valid_mask & (df['last_close'] >= df['ma10d']) & (df['close'] < df['ma10d'])] -= 8.0
    score.loc[valid_mask & (df['open'] > df['close'])] -= 5.0
    score.loc[valid_mask & (df['open'] > df['close']) & ((df['close'] < df['ma5d']) | (df['close'] < df['ma10d']))] -= 5.0
    score.loc[valid_mask & (df['open'] == df['high'])] -= 10.0
    score.loc[valid_mask & (percent_change < -5)] -= 8.0

    # ====================
    # 4️⃣ lastdu4 波动幅度辅助加分
    # ====================
    mask_du4_1 = valid_mask & (df['high'] > df['high4']) & (df['lastdu4'] <= 15)
    mask_du4_2 = valid_mask & (df['high'] > df['high4']) & (df['lastdu4'] > 15) & (df['lastdu4'] <= 40)
    score.loc[mask_du4_1] += 30
    score.loc[mask_du4_2] += 18

    return score

def func_compute_percd2021(open, close, high, low,
                           last_open, last_close, last_high, last_low,
                           ma5, ma10, now_vol, last_vol,
                           upper, high4, max5, hmax,
                           lastdu4, code, idate=None):
    init_c = 0.0
    if np.isnan(last_close) or last_close == 0 or np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    vol_ratio = now_vol / last_vol

    # ====================
    # 1️⃣ 刚启动强势股（安全拉升）
    # ====================
    if high > high4 and percent_change > 5 and last_close < high4:
        if high >= open > last_close and close > last_close and close >= high*0.99 and (high < hmax or last_high < hmax):
            if str(code).startswith(('6','0')):
                if percent_change >= 5:
                    init_c += 25.0
                else:
                    init_c += 20.0
            elif str(code).startswith('3'):
                if percent_change >= 6:
                    init_c += 35.0
                else:
                    init_c += 20.0
            elif str(code).startswith(('688','8')):
                if percent_change >= 5:
                    init_c += 35.0
                else:
                    init_c += 20.0
            else:
                init_c += 15.0
            if vol_ratio < 2:
                init_c += 15.0
            else:
                init_c += 2.0
        else:
            init_c += 15.0

    # ====================
    # 2️⃣ 收盘价突破与高点
    # ====================
    if close > last_close:
        init_c += 1.0
    if high > last_high:
        init_c += 1.0
    if close >= high*0.998:
        init_c += 5.0
        if vol_ratio > 2:
            init_c += 5.0
    if low > last_low:
        init_c += 1.0
    if last_close <= upper and close > upper:
        init_c += 10.0
        if open > last_high and close > open:
            init_c += 10.0
    elif close >= upper:
        init_c += 5.0
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    if high > high4:
        init_c += 3.0
    if percent_change > 3 and close >= high * 0.95 and high > max5 and high > high4:
        init_c += 5.0
    if hmax is not None and high >= hmax:
        init_c += 20.0
    if low > last_high:
        init_c += 20.0
        if close > open:
            init_c += 5.0

    # ====================
    # 低开高走 & 放量 & MA5
    # ====================
    if open == low:
        if open < last_close and open >= ma5 and close > open:
            init_c += 15.0
        if close > open:
            init_c += 8.0
        if vol_ratio > 2:
            init_c += 5.0
    if percent_change > 5:
        init_c += 8.0

    # ====================
    # 3️⃣ 减分项
    # ====================
    if close < last_close:
        init_c -= 1.0
    if low < last_low:
        init_c -= 3.0
    if close < last_close and now_vol > last_vol:
        init_c -= 8.0
    if last_close >= ma5 and close < ma5:
        init_c -= 5.0
    if last_close >= ma10 and close < ma10:
        init_c -= 8.0
    if open > close:
        init_c -= 5.0
        if close < ma5 or close < ma10:
            init_c -= 5.0
    if open == high:
        init_c -= 10.0
    if percent_change < -5:
        init_c -= 8.0

    # ====================
    # 4️⃣ lastdu4 波动幅度辅助加分
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 15:
            init_c += 30
        elif 15 < lastdu4 <=40:
            init_c += 18

    return init_c

def func_compute_percd2021_google(open, close, high, low, last_open, last_close, last_high, last_low, ma5, ma10, now_vol, last_vol, upper, high4, max5, hmax, lastdu4, code, idate=None):
    """
    根据一系列股票交易行为计算综合得分。

    Args:
        open (float): 今日开盘价
        close (float): 今日收盘价
        high (float): 今日最高价
        low (float): 今日最低价
        last_open (float): 昨日开盘价 (虽然未使用，但参数保留以匹配顺序)
        last_close (float): 昨日收盘价
        last_high (float): 昨日最高价
        last_low (float): 昨日最低价
        ma5 (float): 5日移动平均线
        ma10 (float): 10日移动平均线
        now_vol (float): 今日成交量
        last_vol (float): 昨日成交量
        upper (float): 布林线上轨值
        high4 (float): 4日前的最高价
        max5 (float): 5日前的最高价
        hmax (float): 历史最高价
        lastdu4 (float): 前4日的涨幅
        code (str): 股票代码
        idate (str): 日期 (可选)

    Returns:
        float: 综合得分
    """
    init_c = 0.0
    
    # 参数有效性检查
    if np.isnan(last_close) or last_close == 0:
        return 0
    if np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    vol_ratio = now_vol / last_vol
    
    # ====================
    # 加分项（积极信号）
    # ====================
    
    # 收盘价大于前日收盘价
    if close > last_close:
        init_c += 1.0
    
    # 最高价大于前日最高价
    if high > last_high:
        init_c += 1.0
        
    # 收最高价（收盘价等于最高价）
    if close == high:
        init_c += 5.0
        if vol_ratio > 2: # 配合放量涨停给更高分
            init_c += 5.0

    # 最低价大于前日最低价
    if low > last_low:
        init_c += 1.0

    # 收盘价突破布林线上轨
    if last_close <= upper and close > upper:
        init_c += 10.0
        if open > last_high and close > open:
            init_c += 10.0
    elif close >= upper:
        init_c += 5.0
        
    # 成交量温和上涨
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    
    # 大于high4加权重分
    if high > high4:
        init_c += 3.0
    
    # 一个大阳线，大于前几日
    if percent_change > 3 and close >= high * 0.95:
        if high > max5 and high > high4:
            init_c += 5.0
            
    # 历史高点突破
    if hmax is not None and high >= hmax:
        init_c += 20.0 # 突破历史高点给最高分

    # 每日高开高走，无价格重叠 (low > last_high)
    if low > last_high:
        init_c += 20.0 # 强势跳空，权重最高
        if close > open:
            init_c += 5.0
            
    # 开盘价就是最低价 (open == low) 加分
    if open == low:
        if open < last_close and open >= ma5 and close > open:
            init_c += 15.0 # 低开高走且开盘在 ma5 之上，强启动
        elif close > open:
            init_c += 8.0 # 只要是开盘即最低的上涨，都加分
        if vol_ratio > 2: # 配合放量再加分
            init_c += 5.0
    
    # 大幅上涨（加分权重）
    if percent_change > 5:
        init_c += 8.0
    
    # ====================
    # 减分项（消极信号）
    # ====================

    # 收盘价小于前日收盘价
    if close < last_close:
        init_c -= 1.0
        
    # 最低价小于前日最低价（创新低）
    if low < last_low:
        init_c -= 3.0
        
    # 放量下跌（下跌且成交量大于昨日）
    if close < last_close and now_vol > last_vol:
        init_c -= 8.0 # 权重更高
    
    # 下破 ma5 减分
    if last_close >= ma5 and close < ma5:
        init_c -= 5.0
    
    # 下破 ma10 减分
    if last_close >= ma10 and close < ma10:
        init_c -= 8.0

    # 高开低走 (open > close) 减分
    if open > close:
        init_c -= 5.0
        if close < ma5 or close < ma10:
            init_c -= 5.0
            
    # 开盘价就是最高价 (open == high) 减分
    if open == high:
        init_c -= 10.0 # 当天走势疲弱，最高分时减分
    
    # 大幅下跌（减分权重）
    if percent_change < -5:
        init_c -= 8.0

    # ====================
    # 原始代码中关于 lastdu4 的逻辑 (保持不变)
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 1.12:
            init_c += 10
        elif 1.12 < lastdu4 <= 1.21:
            init_c += 8

    return init_c
    
def func_compute_percd2021_nogoogle( open, close,high, low,lastopen, lastclose,lasthigh, lastlow, ma5,ma10,nowvol=None,lastvol=None,upper=None,high4=None,max5=None,hmax=None,lastdu4=None,code=None,idate=None):
    initc = 0
    percent_idx = 2
    vol_du_idx = 1.2
    close_du = 0
    vol_du = 0
    top_max_up = 10
    if np.isnan(lastclose) or lastclose == 0:
        return 0
    if np.isnan(lastclose):
        percent = round((close - open)/open*100,1)
        lastp = 0
    else:
        percent = round((close - lastclose)/lastclose*100,1)
        lastp = round((lastclose - lastopen)/lastclose*100,1)

        
    if  low > 0 and  lastclose > 0 and lastvol > 0 and lasthigh > 1.0 and lastlow > 1.0 and lasthigh > 0 and lastlow > 0:
        percent = round((close - lastclose)/lastclose*100,1)
        # now_du = round((high - low)/low*100,1)
        close_du = round((high - low)/low*100,1)
        # last_du = round((lasthigh - lastlow)/lastlow*100,1)
        # volratio = round((nowvol / lastvol),1)
        vol_du = round((nowvol)/lastvol,1)

        # if idate == "2022-11-28":

        if (percent > percent_idx and low > lastlow and (close_du > percent_idx or vol_du > vol_du_idx)) or (high > lasthigh and (low > lastlow and close > ma5) ):
            initc +=1
            # if  close_du > 5:
            #     initc +=0.1
        # elif percent < -percent_idx or (percent < 0 and close_du > 3):
        elif percent < -percent_idx:
            initc -=1
            # if close > open:
            #     #下跌中继,或者止跌信号
            #     initc +=3
            # if  close_du > 5:
            #     initc -=0.1

        # if percent >0 and open >= lastclose and close == high and close > ma5:
        #     initc +=1
        #     if close > ma5:
        #         if close < ma5*1.1:
        #             initc +=3*vol_du
        #         elif close < ma5*1.2:
        #             initc +=2*vol_du
        #         else:
        #             initc+=2

        # elif percent > 3 and low >= lastlow and high > lasthigh:
        #     initc +=2

        # elif percent > 3 and close_du > 9 and vol_du > 2:
        #     initc += 1*vol_du
        # elif percent > 2 :
        #     initc +=1
        # elif percent > 0  and open > ma5 and open > ma10 :
        #     initc +=1
        #     if  vol_du < 0.6:
        #         initc +=0.1
        # elif low < lastlow and high < lasthigh:
        #     initc -=1
        # elif percent < -5 and low < lastlow:
        #     initc -=2
        # elif percent < 0 and close < ma5 and close < ma10:
        #     initc -=0.51
        # else:
            # initc -=1
    elif  np.isnan(lastclose) :
        if close > open:
            initc +=percent
        else:
            initc -=percent

    # open, close,high, low,lastopen, lastclose,lasthigh, lastlow, 
    # ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None

    if  np.isnan(lastclose):
        if percent > 3 and close > ma5 and high > ma10:
            initc +=2
    else:

        if close > lasthigh:
            initc +=0.1
            # if  ma5 > ma10:
            #     initc +=0.1
            # else:
            #     initc -=0.11
        elif close < lastlow:
            initc -=0.1

        if low > lastlow:
            initc +=0.1
            if high >lasthigh:
                initc +=0.1
                
        if high > lasthigh and close > lasthigh and percent > 3 and ma5 > ma10:

            if lastp < -2:
                initc +=12
            else:
                initc +=2
            if (open >= low or (open >lastclose and close > lasthigh)) and close >= high*0.92:
                initc +=2
                if lastclose >= lasthigh*0.98 or lastclose > (lasthigh + lastlow)/2:
                    initc +=2
                    if close_du > 5 and vol_du > 0.8 and vol_du < 2.2:
                        initc +=5
            elif low > lasthigh:
                initc +=2
            elif close == high:
                initc +=1

            if hmax is not None and high >= hmax:
                # if idate == '300093':
                #     import ipdb;ipdb.set_trace()

                if high4 is not None and max5 is not None:
                    if hmax > high4 and high4 > max5:
                        initc +=10
                else:
                    initc +=3

            if high4 is not None and (high >= high4 or (get_work_time_duration() and high >high4)):

                if lastdu4 is not None:
                    if lastdu4 <= 1.12:
                        initc +=10
                    elif lastdu4 > 1.12 and lastdu4 <= 1.21:
                        initc +=8
                    elif lastdu4 > 1.21 and lastdu4 <= 1.31:
                        initc +=5
                    elif lastdu4 > 1.31 and lastdu4 <= 1.5:
                        initc +=3
                    else:
                        initc +=2

                if max5 is not None and high >= max5:
                    initc +=5
                    # if hmax is not None and close > hmax:
                    #     initc +=3
                    #     lastMax = max(high4,max5,hmax)
                    #     if close >= lastMax and lastclose < lastMax or (not get_work_time_duration() and high >=lastMax):
                    #         if lastdu4 is not None:
                    #             if lastdu4 <= 1.05:
                    #                 initc +=10
                    #             elif lastdu4 > 1.05 and lastdu4 <= 1.1:
                    #                 initc +=8
                    #             elif lastdu4 > 1.1 and lastdu4 <= 1.2:
                    #                 initc +=5
                    #             elif lastdu4 > 1.2 and lastdu4 <= 1.3:
                    #                 initc +=3
                    #             else:
                    #                 initc +=2
                    #         else:
                    #             initc +=1
                    #     else:
                    #         initc +=3
                    #     if close == high:
                    #         initc +=2
                    #     elif close >=high*0.99:
                    #         initc +=2

            # if (lastclose <= upper and high >= upper) | ( ((lastclose >= upper) | (lastp >= 5))):
            if (lastclose <= upper and high >= upper) | ( ((lastclose >= upper) | (lastp >= 5))):
                initc +=percent
                if high4 is not None and hmax is not None:
                    lastMax = max(high4,max5,hmax)
                    if lasthigh >= lastMax:
                        initc += 5 + abs(lastp)
                    if lastMax==hmax and high4 > max5 and high4 < hmax:
                        initc += 5

    if GlobalValues().getkey('percdf') is not None:
        # if code == '601857':
        #     import ipdb;ipdb.set_trace()
        if code in GlobalValues().getkey('percdf').index:
            lastdf = GlobalValues().getkey('percdf').loc[code]
            # if code == '920445':
            #     print(f'{code}lastdf:{lastdf.T}')
            # if isinstance(lastdf,pd.DataFrame):
            #     lastdf = lastdf.reset_index().drop_duplicates('code').set_index('code')
            #     log.error(f'code:{code} count:{lastdf.shape}')
            if percent > 2 and len(lastdf) > 0 and  isinstance(lastdf,pd.Series):
                if lastdf.lasth1d < lastdf.lasth2d < lastdf.lasth3d:
                    if close > lastdf.lasth1d:
                        initc += 30
                        if lastdf.lasth3d < lastdf.lasth4d:
                            initc += 30
                            
                            if lastdf.lasth4d < lastdf.lasth5d:
                                initc += 30
                                if lastdf.lasth5d < lastdf.lasth6d:
                                    initc += 30
                    if low < lastdf.ma51d and high > lastdf.ma51d:
                        initc += 50
                elif lastdf.lasth2d < lastdf.lasth3d < lastdf.lasth4d:
                    if close > lastdf.lasth1d > lastdf.lasth2d:
                        initc += 25
                        if lastdf.lasth3d < lastdf.lasth4d:
                            initc += 30
                            if lastdf.lasth4d < lastdf.lasth5d:
                                initc += 30
                                if lastdf.lasth5d < lastdf.lasth6d:
                                    initc += 30
                    if low < lastdf.ma51d and high > lastdf.ma51d:
                        initc += 50
                                     
                elif lastdf.lasth1d > lastdf.lasth2d > lastdf.lasth3d and lastdf.ma51d < lastdf.lastl1d < lastdf.ma51d*1.02 :
                    initc += 50
                    if lastdf.ma51d < lastdf.lastl1d < lastdf.ma51d*1.02:
                        initc += 30
            else:
                log.warn(f'lastdf is None :{code}')
        # else:
        #     log.info("check lowest in percdf:%s"%(code))
            # print("lowest:%s"%(code),end=' ')

    return round(initc,1)

def WriteCountFilter_cct(df, op='op', writecount=5, end=None, duration=10):
    codel = []
    # market_value = cct.GlobalValues().getkey('market_value')
    # market_key = cct.GlobalValues().getkey('market_key')
    # if market_key == '2':
    #     market_value_perd = int(market_value) * 10
    if str(writecount) != 'all' and isDigit(writecount):
        if end is None and int(writecount) > 0:
            # if int(writecount) < 101 and len(df) > 0 and 'percent' in df.columns:
            if int(writecount) < 101 and len(df) > 0:
                codel = df.index[:int(writecount)].tolist()
                # market_value = cct.GlobalValues().getkey('market_value')
                # market_key = cct.GlobalValues().getkey('market_key')
                # if market_key == '2':
                #     # market_value_perd = int(market_value) * 9.8
                #     market_value_perd = 9.8
                #     dd=df[ df['per%sd'%(market_value)] > market_value_perd ]
                #     df_list=dd.index.tolist()
                #     for co in df_list:
                #         if co not in codel:
                #             codel.append(co)
            else:
                if len(str(writecount)) >= 4:
                    codel.append(str(writecount).zfill(6))
                else:
                    print("writeCount DF is None or Wri:%s" % (writecount))
        else:
            if end is None:
                writecount = int(writecount)
                if writecount > 0:
                    writecount -= 1
                codel.append(df.index.tolist()[writecount])
            else:
                writecount, end = int(writecount), int(end)

                if writecount > end:
                    writecount, end = end, writecount
                if end < -1:
                    end += 1
                    codel = df.index.tolist()[writecount:end]
                elif end == -1:
                    codel = df.index.tolist()[writecount::]
                else:
                    if writecount > 0 and end > 0:
                        writecount -= 1
                        end -= 1
                    codel = df.index.tolist()[writecount:end]
    else:
        if df is not None and len(df) > 0:
            codel = df.index.tolist()
    return codel

Resample_top = {'d':'top_all','3d':'top_all_3d',
                      'w':'top_all_w','m':'top_all_m'}
                      
def re_find_chinese(cmd):
    re_words = re.compile(u"[\u4e00-\u9fa5]+")
    result = re.findall(re_words, cmd)
    return result

def evalcmd(dir_mo,workstatus=True,Market_Values=None,top_temp=pd.DataFrame(),block_path=None,orderby='percent',top_all=None,top_all_3d=None,top_all_w=None,top_all_m=None,resample='d',noformat=False):
    end = True
    import readline
    import rlcompleter
    # readline.set_completer(cct.MyCompleter(dir_mo).complete)
    for top_key in Resample_top.keys():
        top = eval(Resample_top[top_key])
        if top is not None and len(top) > 0 and 'lastp1d' in top.columns:
            if  top.dff[0] == 0 or top.close[0] == top.lastp1d[0]:
                top['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),top['buy'].values, top['df2'].values)))
                top['percent'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),top['buy'].values, top['lastp2d'].values)))
            if  top.volume[0] > 100 and top.volume[-1] > 100:
                if top_key == 'd':
                    ratio_t = 1 
                elif top_key == '3d':
                    ratio_t = 1.5 
                elif top_key == 'w':
                    ratio_t = 2.5 
                elif top_key == 'm':
                    ratio_t = 10
                top['volume'] = (list(map(lambda x, y: round(x / y*ratio_t, 1), top['volume'].values, top.last6vol.values)))
            if 'b1_v' not in top.columns:
                top = combine_dataFrame(top, top_temp.loc[:,['b1_v','a1_v']], col=None, compare=None, append=False)
    readline.parse_and_bind('tab:complete')
    tempdf=[]
    while end:
        # cmd = (cct.cct_raw_input(" ".join(dir_mo)+": "))
        cmd = (cct_raw_input(": ")).strip()
        if len(top_temp) == 0:
            workstatus = False
            top_temp = top_all
        code=ct.codeQuery if workstatus else ct.codeQuery_work_false
        index_status = False
        if len(cmd) == 0:
            # code='最近两周振幅大于10,日K收盘价大于5日线,今日涨幅排序'
            # code='周线2连阳,最近三周振幅大于10,日K收盘价大于5日线,今日涨幅排序'
            # code='日K,4连阳以上,4天涨幅排序,今天阳线'
            # code={"4周新高" : "top_temp.query('close > high4 and lastp1d < hmax and low > lastl1d and lastl1d < ma51d and close >lastp2d')",\
            #       "5周新高" : "top_temp.query('close > max5 and lastp1d < hmax and low > lastl1d and lastl1d < ma51d and close >lastp2d')",\
            #       "K线2连阳"   : "top_temp.query('close > lastp1d and  lastp1d > lastp2d and close >ma51d')",\
            #       "K线连阳"    : "top_temp.query('high > lasth1d and  lasth1d > lasth2d and low >=ma51d')",\
            #       "K线反包"    : "top_temp.query('close > lastp1d and  lastp1d < lastp2d and close >ma51d')"}
            index_status = True
            for idx in range(len(code.keys())):
                id_key = list(code.keys())[idx]
                print("%s: %s %s"%(idx+1,id_key,code[id_key]))
            # for key in code.keys():
            #     print("%s: %s"%(key,code[key]))

            # list(code.keys())
            initkey= list(code.keys())[ct.initkey]
            print(f"index:{ct.initkey+1}:{initkey}: {code[initkey]}")
            # cmd=code[initkey]
            GlobalValues().setkey('tempdf',code[initkey])
            cmd=ct.codeQuery_show_cct(initkey,Market_Values,workstatus,orderby)
            # print(" ".join(list(code.keys())))
        elif len(cmd) <= 2 and cmd.isdigit() and int(cmd) < len(code.keys())+1:
            # idx = int(cmd)+1 if int(cmd) == 0 else int(cmd)
            index_status = True
            idx = int(cmd) - 1
            # print(f"idx:{idx}")
            initkey =  list(code.keys())[idx]
            print(f"\n{initkey}: {code[initkey]}")
            # cmd = code[idxkey]
            GlobalValues().setkey('tempdf',code[initkey])
            if code[initkey].find('filter') > 0:
                cmd = code[initkey]
            else:
                cmd=ct.codeQuery_show_cct(initkey,Market_Values,workstatus,orderby)
        # cmd = (cct.cct_raw_input(dir_mo.append(":")))
        # if cmd == 'e' or cmd == 'q' or len(cmd) == 0:
        if cmd == 'e' or cmd == 'q':
            break
        elif cmd.startswith('w') or cmd.startswith('a') or cmd.startswith('rw') or cmd.startswith('ra'):
            if not cmd.startswith('r') and GlobalValues().getkey('tempdf') is not None:
                tempdf = eval(GlobalValues().getkey('tempdf')).sort_values(orderby, ascending=False)
            else:
                checkcmd = 'q'
                if cmd.startswith('rw') or cmd.startswith('ra'):
                    historyLen=readline.get_current_history_length()
                    idx=1
                    while 1:
                        cmd2 = readline.get_history_item(historyLen-idx)
                        if cmd2 is None:
                            break
                        elif len(cmd2) < 20:
                            idx+=1
                            continue
                        print(f'cmd : {cmd2}',end=' ')
                        checkcmd=cct_raw_input(" is OK ? Y or N or q:")
                        if checkcmd == 'y' or checkcmd == 'q' or idx > historyLen-2:
                            break
                        else:
                            idx+=1

                    if  checkcmd == 'q':
                        print(f'checkcmd:{cmd} quit')
                        continue
                    elif  checkcmd == 'y':
                        # hdf_wri = cct_raw_input("to write Y or N:")
                        # if hdf_wri == 'y':
                        cmdlist=cmd.split()
                        if cmd.startswith('rw'):
                            cmd_ = 'w '
                        else:
                            cmd_ = 'a '

                        cmd2_list = cmd2.split()
                        if len(cmd2_list) > 1:
                            orderby_t = cmd2_list[-1]
                            # if orderby_t in list(dir(top_temp)):
                            if orderby_t in top_temp.columns:
                                orderby = orderby_t
                                # doubleCmd = True
                                cmd2 = cmd2[:cmd2.rfind(orderby_t)]
                            elif re.findall(r'^[a-z\d]*', orderby_t)[0] == orderby_t:
                                # doubleCmd = True
                                cmd2 = cmd2[:cmd2.rfind(orderby_t)]

                        tempdf = eval(cmd2).sort_values(orderby, ascending=False)
                        if isinstance(tempdf,pd.DataFrame):
                            GlobalValues().setkey('tempdf',cmd2)

                        if len(cmdlist) > 1:
                            # ' '.join([aa.split()[i] for i in range(1,len(aa.split()))])
                            log.debug(f'cmd:{cmd}')
                            cmd =cmd_ + ' '.join([cmd.split()[i] for i in range(1,len(cmd.split()))])
                            print(f'cmd:{cmd}')
                        else:
                            cmd = cmd_
                    else:
                        print("return shell")
                        continue
                else:
                    continue
                    
            if len(tempdf) >  0:
                args = writeArgmain_block().parse_args(cmd.split())
                codew = WriteCountFilter_cct(
                    tempdf, 'ra', writecount=args.dl)
                if args.blk is not None:
                    block_path = get_tdx_dir_blocknew() + f'{args.blk}.blk'
                if args.code == 'a':
                    write_to_blocknew(block_path, codew)
                    # sl.write_to_blocknew(all_diffpath, codew)
                else:
                    # codew = stf.WriteCountFilter(top_temp)
                    write_to_blocknew(block_path, codew, append=False,keep_last=0)
                    # sl.write_to_blocknew(all_diffpath, codew, False)
                print("wri ok:%s" % block_path)
                # cct.GlobalValues().setkey('tempdf',None)
                sleeprandom(ct.duration_sleep_time / 10)
            else:
                print(f'tempdf is None cmd:{cmd}')
            
        elif len(cmd) == 0:
            continue
        else:
            try:
                if cmd.startswith('tempdf'):
                    if GlobalValues().getkey('tempdf') is not None:
                        tempdf = eval(GlobalValues().getkey('tempdf')).sort_values(orderby, ascending=False)
                        # print((eval(cmd)))

                if not cmd.find(' =') < 0:
                    # cmd = ct.codeQuery_show_single(cmd,Market_Values,orderby='percent')
                    # import ipdb;ipdb.set_trace()
                    # print(cmd)
                    # exec(cmd)
                    exec(cmd)
                elif  cmd.find('filter') > 0:
                    print((eval(cmd))) 
                else:
                    
                    doubleCmd=False
                    log.debug(f'cmd.split():{cmd}')
                    cmd_list = cmd.split()
                    # if len(cmd_list) > 1:
                    #     orderby_t = cmd_list[-1]
                    #     # if orderby_t in list(dir(top_temp)):
                    #     if orderby_t in top_temp.columns:
                    #         orderby = orderby_t
                    #         # doubleCmd = True
                    #         cmd = cmd[:cmd.rfind(orderby_t)]
                    #     elif re.findall(r'^[a-z\d]*', orderby_t)[0] == orderby_t:
                    #         # doubleCmd = True
                    #         cmd = cmd[:cmd.rfind(orderby_t)]
                    re_words = re.compile(u"[\u4e00-\u9fa5]+")
                    if len(cmd_list) == 1 and len(re.findall(re_words, cmd)) > 0:
                        cmd = f'top_all {cmd}'
                        cmd_list = cmd.split()
                    category_search = False

                    if len(cmd_list) > 1 and cmd.find('category') < 0:
                        orderby_t = cmd_list[-1]
                        if len(re.findall(re_words, orderby_t)) > 0:
                            category_search = True
                            search_key = f'category.str.contains("{cmd_list[-1]}")'
                            if cmd.find('query') < 0:
                                cmd = f"{cmd_list[0]}.query('close > 0') {orderby_t}"
                            cmd = cmd[:cmd.rfind(orderby_t)].replace("')",f" and {search_key}')")
                            print(f'cmd: {cmd}')
                        else: 
                            if orderby_t in top_temp.columns:
                                orderby = orderby_t
                                # doubleCmd = True
                                cmd = cmd[:cmd.rfind(orderby_t)]
                            elif re.findall(r'^[a-z\d]*', orderby_t)[0] == orderby_t:
                                # doubleCmd = True
                                cmd = cmd[:cmd.rfind(orderby_t)]

                    if category_search:
                        check_all = cmd.split('.')[-3]
                        check_s = re.findall(r'^[a-zA-Z\d]*', check_all)[0]
                    else:
                        check_all = cmd.split('.')[-1]
                        check_s = re.findall(r'^[a-zA-Z\d]*', check_all)[0]

                    # if (cmd.startswith('tempdf') or cmd.startswith('top_temp')) and  cmd.find('sort') < 0:
                    

                    if (cmd.find('.loc') > 0 and cmd.find(':') > 0) or (cmd.find('.loc') < 0 and (cmd.startswith('tempdf') or cmd.startswith('top_temp') or cmd.startswith('top_all'))) and  check_s not in top_temp.columns:
                        if orderby not in ['topR','percent']and orderby in top_temp.columns:
                            top_temp[orderby] = top_temp[orderby].astype(int)
                            top_all[orderby] = top_all[orderby].astype(int)
                            
                        if (cmd.startswith('tempdf') or cmd.startswith('top_temp') or cmd.startswith('top_all')) and  check_s not in top_temp.columns:
                            # if cmd.split('.')[-1] not in list(dir(top_temp)) and cmd.find('format_for_print_show') < 0:
                            if (check_s == 'query' or  check_s not in list(dir(top_temp))) and cmd.find('format_for_print_show') < 0:
                            
                                tempdf = eval(cmd)
                                if isinstance(tempdf,pd.DataFrame):
                                    GlobalValues().setkey('tempdf',cmd)
                                if cmd.find('query') > 0:
                                    if doubleCmd:
                                        write_evalcmd2file(evalcmdfpath,cmd+orderby_t)
                                    else:
                                        write_evalcmd2file(evalcmdfpath,cmd)
                                try:
                                    cmd = ct.codeQuery_show_single(cmd,Market_Values,orderby=orderby,noformat=noformat)
                                except Exception as e:
                                    print("Exception:", e)
                                    traceback.print_exc()
                                    # raise e
                        elif  check_s  != orderby and cmd.find('sort_values') < 0 and (check_s  in list(dir(top_temp)) or check_s in top_temp.columns) :
                            cut_tail = cmd.split('.')[-1]
                            # cmd_head = cmd.replace(cut_tail,'')
                            cmd_head = cmd[:cmd.rfind(cut_tail)]
                            cmd = f"{cmd_head}sort_values('{orderby}', ascending=False).{cut_tail}"  

                    print((eval(cmd))) 
                if index_status:
                    idx = 0
                    cut_d = 7
                    for idx_k in range(len(code.keys())):
                        id_key = list(code.keys())[idx_k]
                        idx+=1
                        if idx >cut_d and idx%cut_d == 1:
                            # print("\t\t",end='')
                            print("%s:%s "%(idx_k+1,id_key))
                        else:
                            print("%s:%s "%(idx_k+1,id_key),end="")
                        # if idx%4 == 0:
                        #     print(f'\\')
                    print(f"\n{initkey}: {code[initkey]}")

                print('')
            except Exception as e:
                print(e)
                # evalcmd(dir_mo)
                # break


def func_compute_percd2021_2022mod( open, close,high, low,lastopen, lastclose,lasthigh, lastlow, ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None):
    # down_zero, down_dn, percent_l = 0, 0, 2
     # (1 if ( ((c >= op) and ((c - lc)/lc*100 >= 0)) or (c >= op and c >=m5a) ) else down_dn)
    # df['vol'],df['vol'].shift(1),df['upper']

    initc = 0
    if  0 < lastclose < 1000 and lasthigh != 1.0 and lastlow != 1.0 and lasthigh != 0 and lastlow != 0:
#        close = round(close, 1)
#        lastp = round(lastp, 1)
#        op = round(op, 1)
#        lastopen = round(lastopen, 1)
#        lasth = round(lasth, 1)
#        lastl = round(lastl, 1)
        percent = round((close - lastclose)/lastclose*100,1)
        # now_du = round((high - low)/low*100,1)
        close_du = round((high - low)/low*100,1)
        # last_du = round((lasthigh - lastlow)/lastlow*100,1)
        # volratio = round((nowvol / lastvol),1)
        vol_du = round((nowvol)/lastvol,1)

        if percent > 1:
            initc +=1
            if  close_du > 5:
                initc +=0.1
        elif percent < -1:
            initc -=1
            if  close_du > 5:
                initc -=0.1
                
        # if percent >0 and open >= lastclose and close == high and close > ma5:
        #     initc +=1
        #     if close > ma5:
        #         if close < ma5*1.1:
        #             initc +=3*vol_du
        #         elif close < ma5*1.2:
        #             initc +=2*vol_du
        #         else:
        #             initc+=2

        # elif percent > 3 and low >= lastlow and high > lasthigh:
        #     initc +=2

        # elif percent > 3 and close_du > 9 and vol_du > 2:
        #     initc += 1*vol_du
        # elif percent > 2 :
        #     initc +=1
        # elif percent > 0  and open > ma5 and open > ma10 :
        #     initc +=1
        #     if  vol_du < 0.6:
        #         initc +=0.1
        # elif low < lastlow and high < lasthigh:
        #     initc -=1
        # elif percent < -5 and low < lastlow:
        #     initc -=2
        # elif percent < 0 and close < ma5 and close < ma10:
        #     initc -=0.51
        # else:
            # initc -=1
    elif  np.isnan(lastclose) :
        if close > open:
            initc +=1

    # open, close,high, low,lastopen, lastclose,lasthigh, lastlow, 
    # ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None
    if close > ma5:
        initc +=0.1
        if  ma5 > ma10:
            initc +=0.1
        else:
            initc -=0.11
    else:
        initc -=0.1

    return initc

# import numba as nb
# @numba.jit(nopython=True)
# @nb.autojit
def func_compute_percd2(close, lastp, op, lastopen,lasth, lastl, nowh, nowl,nowvol=None,lastvol=None,upper=None,hmax=None):
    # down_zero, down_dn, percent_l = 0, 0, 2
     # (1 if ( ((c >= op) and ((c - lc)/lc*100 >= 0)) or (c >= op and c >=m5a) ) else down_dn)
    # df['vol'],df['vol'].shift(1),df['upper']
    initc = 0
    if 0 < lastp < 1000 and lasth != 1.0 and lastl != 1.0 and lasth != 0 and lastl != 0:
#        close = round(close, 1)
#        lastp = round(lastp, 1)
#        op = round(op, 1)
#        lastopen = round(lastopen, 1)
#        lasth = round(lasth, 1)
#        lastl = round(lastl, 1)
        percent = round((close - lastp)/lastp*100,1)
        now_du = round((nowh - nowl)/nowl*100,1)
        last_du = round((lasth - lastl)/lastl*100,1)
        volratio = round((nowvol / lastvol),1)
        if volratio > 1.1:
            initc +=1
            if last_du > 2 or now_du >3:
                if percent > 0.8:
                    initc +=1
                # if percent > 5 or (nowvol / lastvol) > 1.5:
                #     initc +=1
                # if percent > 8 and (nowvol / lastvol) > 1.2:
                #     initc +=1
                if percent < -2 and volratio > 1.2:
                    initc -=1
                if nowh >= lasth:
                    initc +=1
                    if close >= nowh*0.98:
                        initc +=1
            if volratio >1.5:
                initc +=1
#            else:
#                if lastp > lastopen and close > op:
#                    initc +=1

        else:
            if last_du > 2 or now_du > 3:
                if percent > 2:
                    initc +=1
#                elif -2 < percent < 1:
#                    initc -=1
#                elif percent < -2:
#                    initc -=1
                if close >= lasth or nowh >= lasth:
                    initc +=1
                    if close >= nowh*0.98:
                        initc +=1
            else:
                if nowl >= op and close > op:
                    initc +=2
                else:
                    initc +=1



        if nowl == op or (op > lastp and nowl > lastp):
            initc +=1
            if lastopen >= lastl:
                initc +=1
            if  nowh > lasth:
                initc +=1
                # if nowh == close:
                #     initc +=1

        if  op > lastp or nowl > lastp:
                initc +=1

        if ((close - lastp)/lastp*100 >= 0):
            if op > lastp:
                initc +=1
                # if nowh == nowl:
                #     initc +=1
                if nowl > lastp:
                    initc +=1
                    if nowl > lasth:
                        initc +=1

                if close > nowh * ct.changeRatio:
                    initc +=1
                    # if lastp == lasth:
                    #     initc +=1

                if (close >= op):
                    initc +=1
                    if (nowh > lasth):
                        initc +=1
                        if (nowl >= lastl):
                            initc +=1
                else:
                    initc -=1
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            else:
                initc +=1
                if op >= nowl*0.995:
                    initc +=1
                    if (nowh > lasth):
                        initc +=1
                        if close > nowh * ct.changeRatio:
                            initc +=1
                            if (nowl >= lastl):
                                initc +=1

        else:
            if op < lastp:
                if (close >= op):
                    if  nowl > lastl:
                        initc +=1
                else:
                    initc -=1
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            else:
                if (close < op):
                    if (nowh < lasth):
                        initc -=1
                    if  nowl < lastl:
                        initc -=1
                else:
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            if nowh < lastp:
                initc -=1
                if nowh < lastl:
                    initc -=1

        if hmax is not None:
            if cumin is not None:
                if volratio > 4:
                    if cumin < 2:
                        initc += 8
                    elif cumin > 5:
                        initc -= 2
                elif lastopen >= lastl:
                    # initc +=1
                    # if op >= nowl:
                    #     initc +=1
                    if nowh >= hmax:
                        initc +=2
            # if lastopen >= lastl:
            #     initc +=1
            #     if op >= nowl:
            #         initc +=1
            # if nowh >= hmax:
            #     initc +=1

    return initc

def func_compute_percdS(close, lastp, op, lastopen,lasth, lastl, nowh, nowl,nowvol=None,lastvol=1,hmax=None,cumin=None):
    # down_zero, down_dn, percent_l = 0, 0, 2
     # (1 if ( ((c >= op) and ((c - lc)/lc*100 >= 0)) or (c >= op and c >=m5a) ) else down_dn)
    initc = 0
    if lasth != 1.0 and lastl != 1.0 and lasth != 0 and lastl != 0:
        close = round(close, 1)
        lastp = round(lastp, 1)
        op = round(op, 1)
        lastopen = round(lastopen, 1)
        lasth = round(lasth, 1)
        lastl = round(lastl, 1)
        percent = round((close - lastp)/lastp*100,1)
        now_du = round((nowh - nowl)/nowl*100,1)
        last_du = round((lasth - lastl)/lastl*100,1)
        volratio = round((nowvol / lastvol),1)
        if volratio > 1.1:
            if last_du > 3 or now_du >3:
                if percent > 2:
                    initc +=1
                # if percent > 5 or (nowvol / lastvol) > 1.5:
                #     initc +=1
                # if percent > 8 and (nowvol / lastvol) > 1.2:
                #     initc +=1
                if percent < -2 and volratio > 1.2:
                    initc -=1
                if close >= lasth*0.98:
                    initc +=1
                    if close >= nowh*0.98:
                        initc +=1
            else:
                if lastp > lastopen and close > op:
                    initc +=1

        else:
            if last_du > 3 or now_du > 3:
                if percent > 2:
                    initc +=1
                elif -2 < percent < 1:
                    initc -=1
                elif percent < -2:
                    initc -=2
                if close >= lasth:
                    initc +=1
                    if close >= nowh*0.98:
                        initc +=1
            else:
                if lastp > lastopen and close > op:
                    initc +=1



        if nowl == op or (op > lastp and nowl > lastp):
            initc +=1
            if lastopen >= lastl:
                initc +=1
            if  nowh > lasth:
                initc +=1
                # if nowh == close:
                #     initc +=1

        if  op > lastp or nowl > lastp:
                initc +=1

        if ((close - lastp)/lastp*100 >= 0):
            if op > lastp:
                initc +=1
                # if nowh == nowl:
                #     initc +=1
                if nowl > lastp:
                    initc +=1
                    if nowl > lasth:
                        initc +=1

                if close > nowh * ct.changeRatio:
                    initc +=1
                    # if lastp == lasth:
                    #     initc +=1

                if (close >= op):
                    initc +=1
                    if (nowh > lasth):
                        initc +=1
                        if (nowl >= lastl):
                            initc +=1
                else:
                    initc -=1
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            else:
                initc +=1
                if op >= nowl*0.995:
                    initc +=1
                    if (nowh > lasth):
                        initc +=1
                        if close > nowh * ct.changeRatio:
                            initc +=1
                            if (nowl >= lastl):
                                initc +=1

        else:
            if op < lastp:
                if (close >= op):
                    if  nowl > lastl:
                        initc +=1
                else:
                    initc -=1
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            else:
                if (close < op):
                    if (nowh < lasth):
                        initc -=1
                    if  nowl < lastl:
                        initc -=1
                else:
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            if nowh < lastp:
                initc -=1
                if nowh < lastl:
                    initc -=1

        if hmax is not None:
            if cumin is not None:
                if volratio > 4:
                    if cumin < 2:
                        initc += 8
                    elif cumin > 5:
                        initc -= 2
                elif lastopen >= lastl:
                    # initc +=1
                    # if op >= nowl:
                    #     initc +=1
                    if nowh >= hmax:
                        initc +=11
            # if lastopen >= lastl:
            #     initc +=1
            #     if op >= nowl:
            #         initc +=1
            # if nowh >= hmax:
            #     initc +=1

    return initc


def select_dataFrame_isNull(df):
    is_null = df.isnull().stack()[lambda x: x].index.tolist() 
    return(is_null)

def combine_dataFrame(maindf, subdf, col=None, compare=None, append=False, clean=True):
    '''

    Function: combine_dataFrame

    Summary: 合并DF,Clean:True Clean Maindf else Clean Subdf

    Examples: @
    Attributes: 

        @param (maindf):maindf

        @param (subdf):subdf

        @param (col) default=None: InsertHere

        @param (compare) default=None: InsertHere

        @param (append) default=False: InsertHere

        @param (clean) default=True: InsertHere

    Returns: Maindf

    '''
    times = time.time()
    if maindf is None or len(maindf) < 1:
        log.error(f'maindf is None:{maindf}')
        return maindf
    if subdf is  None or len(subdf) == 0:
        return maindf

    if (isinstance(maindf,pd.Series)):
        maindf = maindf.to_frame()
    if (isinstance(subdf,pd.Series)):
        subdf = subdf.to_frame()
    maindf_co = maindf.columns
    subdf_co = subdf.columns
    maindf = maindf.fillna(0)
    subdf = subdf.fillna(0)
#    if 'ticktime' in maindf.columns:
#        maindf = maindf.dropna()
#        maindf.ticktime = maindf.ticktime.apply(lambda x:str(x).replace(':','')[:4] if len(str(x))==8 else x)
#        maindf.ticktime = maindf.ticktime.astype(int)
#        maindf = maindf[maindf.ticktime < get_now_time_int()+5]
    if not append:

        if 'code' in maindf.columns:
            maindf = maindf.set_index('code')
        if 'code' in subdf.columns:
            subdf = subdf.set_index('code')

        no_index = maindf.drop([inx for inx in maindf.index if inx not in subdf.index], axis=0)
        # 遍历Maindf中subdf没有的index并删除

#        no_index = maindf.loc[subdf.index]
        # if col is not None and compare is not None:
        #     # if col in subdf.columns:
        #     # sub_col = list(set(subdf.columns) - set([col]))

        #     # sub_dif_inx = list(set(subdf.index) - set(maindf.index))
        #     # trandf = subdf.drop(sub_dif_inx,axis=0)
        #     # no_index[compare]=map((lambda x,y:y-x),no_index.couts,trandf.couts)
        #     pass
        #     # no_index[compare]=map((lambda x,y:y-x),eval("subdf.%s"%(col)),eval("no_index.%s"%(col)))
        # else:
        #     sub_col = list(set(subdf.columns) - set())

        drop_sub_col = [col for col in no_index.columns if col in subdf.columns]
        #比较主从的col,两边都有的需要清理一个
        if clean:
            #Clean True时清理maindf的旧数据
            no_index = no_index.drop(drop_sub_col, axis=1)
        else:
            #Clean False时清理subdf columns的数据
            subdf = subdf.drop(drop_sub_col, axis=1)
        if len(subdf.columns) > 0:
            no_index = no_index.merge(subdf, left_index=True, right_index=True, how='left')
            maindf = maindf.drop([inx for inx in maindf.index if inx in subdf.index], axis=0)
            maindf = pd.concat([maindf, no_index], axis=0)
    else:
        #        if len(list(set(maindf.columns)-set()))
        #        if len(maindf) < len(subdf):
        #            maindf,subdf =subdf,maindf
        maindf = maindf.drop([col for col in maindf.index if col in subdf.index], axis=0)
        co_mod = maindf.dtypes[(maindf.dtypes == int) & (list(maindf.dtypes.keys()) != 'ldate') & (list(maindf.dtypes.keys()) != 'kind')]

        for co_t in list(co_mod.keys()):
            if co_t in subdf.columns:
                if maindf.dtypes[co_t] != subdf.dtypes[co_t]:
                    # print maindf.dtypes[co_t] , subdf.dtypes[co_t]
                    # print maindf[co_t],subdf[co_t]
                    # print co_t,maindf.dtypes[co_t]
                    subdf[co_t] = subdf[co_t].astype(maindf.dtypes[co_t])
                    # log.error("col to types:%s" % (maindf.dtypes[co_t]))
            else:
                if append:
                    subdf[co_t] = 0
                    subdf[co_t] = subdf[co_t].astype(maindf.dtypes[co_t])
                    
        maindf = pd.concat([maindf, subdf], axis=0)
        maindf = maindf.fillna(-2)
        if not 'code' in maindf.columns:
            if not maindf.index.name == 'code':
                maindf.index.name = 'code'
        maindf.reset_index(inplace=True)
        maindf.drop_duplicates('code', inplace=True)
        maindf.set_index('code', inplace=True)
#        maindf['timel']=time.time()
    '''
        if 'code' in maindf.columns:
            maindf = maindf.set_index('code')
        if 'code' in subdf.columns:
            subdf = subdf.set_index('code')

        diff_m_sub = list(set(maindf.index) - set(subdf.index))
        same_sub = list(set(subdf.index) & set(maindf.index))
    #    no_index = maindf.drop([inx for inx in maindf.index  if inx not in subdf.index], axis=0)
        maindf = maindf.drop(same_sub, axis=0)

        if col is None:
            sub_col = subdf.columns
        else:
            sub_col = list(set(subdf.columns)-set(maindf.columns))

        same_columns = list(set(subdf.columns) & set(maindf.columns))
    #    maindf.drop([col for col in no_index.columns if col in subdf.columns], axis=1,inplace=True)
        maindf.drop(same_columns, axis=1,inplace=True)
        no_index = no_index.merge(subdf, left_index=True, right_index=True, how='left')
        maindf = maindf.drop([inx for inx in maindf.index  if inx in subdf.index], axis=0)
        maindf = pd.concat([maindf, no_index],axis=0)
    '''
    # maindf = maindf.drop_duplicates()
    log.info("combine df :%0.2f" % (time.time() - times))
    if append:
        dif_co = list(set(maindf_co) - set(subdf_co))
        # if set(dif_co) - set(['nhigh', 'nlow', 'nclose']) > 0 and len(dif_co) > 1:
            # log.info("col:%s %s" % (dif_co[:3], eval(("maindf.%s") % (dif_co[0]))[1]))
    return maindf

if __name__ == '__main__':

    '''
    def readHdf5(fpath, root=None):
        store = pd.HDFStore(fpath, "r")
        print(store.keys())
        if root is None:
            root = store.keys()[0].replace("/", "")
        df = store[root]
        df = apply_col_toint(df)
        store.close()
        return df
    def apply_col_toint(df, col=None):
        if col is None:
            co2int = ['boll', 'op', 'ratio', 'fib', 'fibl', 'df2']
        # co2int.extend([co for co in df.columns.tolist()
        #                if co.startswith('perc') and co.endswith('d')])
            co2int.extend(['top10', 'topR'])
        else:
            co2int = col
        co2int = [inx for inx in co2int if inx in df.columns]

        for co in co2int:
            df[co] = df[co].astype(int)

        return df

    sina_MultiD_path = "G:\\sina_MultiIndex_data.h5"
    h5 = readHdf5(sina_MultiD_path)
    print(sina_MultiD_path)
    h5.shape
    # h5[:1]
    code_muti = '600519'
    # h5.loc[code_muti][:2]

    freq = 'D'
    startime = '09:25:00'
    endtime = '15:01:00'

    time_ratio = get_work_time_ratio()
    time_ratio
    run_col = ['close', 'volume']
    mdf = get_limit_multiIndex_freq(
        h5, freq=freq.upper(),
    col=run_col, start=startime, end=endtime, code=None)
    mdf.shape
    '''
    # rzrq['all']='nan'
    # print(get_last_trade_date('2025-06-01'))
    st_key_sort='3 0 f'
    print(ct.get_market_sort_value_key(st_key_sort))
    import ipdb;ipdb.set_trace()
    query_rule = read_ini(inifile='filter.ini',category='sina_Monitor')
    print(get_today(''))
    get_lastdays_trade_date(1)
    print(f'get_work_day_idx:{get_work_day_idx()}')
    print(get_tdx_dir_blocknew_dxzq(r'D:\MacTools\WinTools\new_tdx2\T0002\blocknew\090.blk'))
    print(f'is_trade_date():{is_trade_date()}')
    print(f'is_trade_date:{is_trade_date_today}')
    print(isDigit('nan None'))
    print("指数的贡献度:",isDigit('指数的贡献度'))

    GlobalValues()
    GlobalValues().setkey('key', 'GlobalValuesvalue')
    print(GlobalValues().getlist())
    import ipdb;ipdb.set_trace()
    
    # print(read_to_indb())
    print(get_trade_date_status())
    print(get_config_value_ramfile(fname='is_trade_date',currvalue=is_trade_date(),xtype='trade_date'))
    print(code_to_symbol_ths('000002'))
    print(get_index_fibl())
    GlobalValues()
    GlobalValues().setkey('key', 'GlobalValuesvalue')
    print(get_work_time())
    print(get_now_time_int())
    print(get_work_duration())
    print((random.randint(0, 30)))
    print(GlobalValues().getkey('key', defValue=None))
    print(get_run_path_tdx('aa'))
    print(get_ramdisk_path(tdx_hd5_name))
    print(get_today(sep='-'))
    from docopt import docopt
    log = LoggerFactory.log
    args = docopt(sina_doc, version='sina_cxdn')
    # print args,args['-d']
    if args['-d'] == 'debug':
        log_level = LoggerFactory.DEBUG
    elif args['-d'] == 'info':
        log_level = LoggerFactory.INFO
    else:
        log_level = LoggerFactory.ERROR
    # log_level = LoggerFactory.DEBUG if args['-d']  else LoggerFactory.ERROR

    # log_level = LoggerFactory.DEBUG
    # log.setLevel(log_level)
    # print tdxblk_to_code('1399001')
    print(tdxblk_to_code('0399001'))
    print(read_to_blocknew('066'))
    # get_terminal_Position(cmd=scriptquit, position=None, close=False)
    # get_terminal_Position('Johnson —', close=True)
    get_terminal_Position(clean_terminal[2], close=True)
    get_terminal_Position(clean_terminal[1], close=True)
    log.info("close Python Launcher")
    s_time = time.time()
    print("last:", last_tddate(2))
    print(get_work_day_status())
    print(get_terminal_Position(cmd='DurationDN.py', position=None, close=False))
    print(get_terminal_Position(cmd='Johnson@', position=None, close=False))
    print(get_terminal_Position(cmd=clean_terminal[1], position=None, close=False))
    print("t:%0.2f" % (time.time() - s_time))
    print(get_ramdisk_path('a', lock=False))
    # print get_work_time_ratio()
    # print typeday8_to_day10(None)
    # write_to_blocknew('abc', ['300380','601998'], append=True)
    print(get_now_time_int())
    print(get_work_duration())
    print(get_today_duration('2017-01-01', '20170504'))
    # print get_tushare_market(market='captops', renew=True,days=10).shape
    # print get_rzrq_code()[:3]
    # times =1483686638.0
    # print get_time_to_date(times, format='%Y-%m-%d')

    # for x in range(1,120,5):
    #     times=time.time()
    #     print sleep(x)
    #     print time.time()-times
    print(get_work_time_ratio())
    print(getCoding('啊中国'.encode("utf16")))
    print(get_today_duration('2017-01-06'))
    print(get_work_day_status())
    import sys
    sys.exit(0)
    print(get_rzrq_code('cxgzx')[:3])
    print(get_rzrq_code('cx')[:3])
    print(get_now_time())
    print(get_work_time_ratio())
    print(get_work_day_status())
    print(last_tddate(days=3))
    for x in range(0, 4, 1):
        print(x)
        print(last_tddate(x))
        # print last_tddate(2)
    print(get_os_system())
    set_console()
    set_console(title=['G', 'dT'])
    input("a")
    # print System.IO.Path
    # print workdays('2010-01-01','2010-05-01')
