# -*- coding:utf-8 -*-
# !/usr/bin/env python

import logging
import os
import pymysql
from sqlalchemy import create_engine
from sqlalchemy.types import NVARCHAR
from sqlalchemy import inspect
import datetime
import sys

# stdout=sys.stdout
# import commonTips as cct
# sys.path.append('../')
# from JohnsonUtil import commonTips as cct
# from JSONData import tdx_data_Day as tdd

# def write_code_to_blk(codew, blk='060'):
#     block_path = tdd.get_tdx_dir_blocknew() + '%s.blk' % (blk)
#     write_blk = 'n'
#     write_blk = cct.cct_raw_input("write blk [Y] or [N]:")
#     if write_blk == 'y' or write_blk == 'Y':
#         hdf5_wri = cct.cct_raw_input(
#             "Rewrite code [Y] or append [N](defalut:N):")
#         if hdf5_wri == 'y' or hdf5_wri == 'Y':
#             append_status = False
#         else:
#             append_status = True
#         if len(codew) > 3:
#             cct.write_to_blocknew(block_path, codew, append_status,
#                                   doubleFile=False, keep_last=0)
#             print("write:%s block_path:%s" % (len(codew), block_path))
#         else:
#             print("write No:%s block_path:%s" % (len(codew), block_path))
#             # ("write error:%s block_path:%s" % (len(codew), block_path))
#     return True

#allday
def groupby_count_code(df):
    df['couts'] = df.groupby('code')['code'].transform('count')
    if 'date' in df.columns:
        df = df.sort_values(by=['couts','date'],ascending=[0,1])
    else:
        df = df.sort_values(by=['couts'],ascending=[0])
    return df

def get_today(sep='-'):
    TODAY = datetime.date.today()
    fstr = "%Y" + sep + "%m" + sep + "%d"
    today = TODAY.strftime(fstr)
    return today

#前一日
def day_last_days(daynow,last=-1):
    return str(datetime.datetime.strptime(daynow, '%Y-%m-%d').date() + datetime.timedelta(last))

#上一个工作日
def last_tddate(days=1):
    # today = datetime.datetime.today().date() + datetime.timedelta(-days)
    if days is None:
        return days
    today = datetime.datetime.today().date()
    # log.debug("today:%s " % (today))
    # return str(today)

    def get_work_day(today):
        day_n = int(today.strftime("%w"))
        if day_n == 0:
            lastd = today + datetime.timedelta(-2)
            # log.debug("0:%s" % lastd)
        elif day_n == 1:
            lastd = today + datetime.timedelta(-3)
            # log.debug("1:%s" % lastd)
        else:
            lastd = today + datetime.timedelta(-1)
            # log.debug("2-6:%s" % lastd)
        return lastd
        # if days==0:
        # return str(lasd)
    lastday = today
    for x in range(int(days)):
        # print x
        lastday = get_work_day(today)
        today = lastday
    return str(lastday)

# 通过数据库链接 engine
def engine():
    return create_engine(MYSQL_CONN_URL)


def engine_to_db(to_db):
    _engine = create_engine(MYSQL_CONN_URL.replace(f'/{db_database}?', f'/{to_db}?'))
    return _engine


# DB Api -数据库连接对象connection，有游标
def conn_with_cursor():
    return conn_not_cursor().cursor()

# DB Api -数据库连接对象connection，无游标
def conn_not_cursor():
    try:
        _db = pymysql.connect(**MYSQL_CONN_DBAPI)
    except Exception as e:
        logging.error(f"database.conn_not_cursor处理异常：{MYSQL_CONN_DBAPI}{e}")
    return _db

# 查询数据
def executeSqlFetch(sql, params=()):
    with conn_with_cursor() as db:
        try:
            db.execute(sql, params)
        except Exception as e:
            logging.error(f"database.executeSqlFetch处理异常：{sql}{e}")

        result = db.fetchall()
        db.close()
        return result
    
# 计算数量
def executeSqlCount(sql, params=()):
    with conn_with_cursor() as db:
        try:
            db.execute(sql, params)
        except Exception as e:
            logging.error(f"database.select_count计算数量处理异常：{e}")

        result = db.fetchall()
        db.close()
        # 只有一个数组中的第一个数据
        if len(result) == 1:
            return int(result[0][0])
        else:
            return 0

db_host = "192.168.1.60"  # 数据库服务主机
db_user = "root"  # 数据库访问用户
db_password = "mariadb"  # 数据库访问密码
db_database = "instockdb"  # 数据库名称
db_port = 3306  # 数据库服务端口
db_charset = "utf8mb4"  # 数据库字符集

# 使用环境变量获得数据库,docker -e 传递
_db_host = os.environ.get('db_host')
if _db_host is not None:
    db_host = _db_host
_db_user = os.environ.get('db_user')
if _db_user is not None:
    db_user = _db_user
_db_password = os.environ.get('db_password')
if _db_password is not None:
    db_password = _db_password
_db_database = os.environ.get('db_database')
if _db_database is not None:
    db_database = _db_database
_db_port = os.environ.get('db_port')
if _db_port is not None:
    db_port = int(_db_port)

MYSQL_CONN_URL = "mysql+pymysql://%s:%s@%s:%s/%s?charset=%s" % (
    db_user, db_password, db_host, db_port, db_database, db_charset)

MYSQL_CONN_DBAPI = {'host': db_host, 'user': db_user, 'password': db_password, 'database': db_database,
                    'charset': db_charset, 'port': db_port, 'autocommit': True}


# try:
#     with pymysql.connect(**MYSQL_CONN_DBAPI) as mydb:
#         mydb.cursor().execute(" select 1 ")
# except Exception as e:
#         logging.error("执行信息：数据库不存在，将创建。")


import pandas as pd
import warnings

warnings.filterwarnings('ignore')


def panda_df(conn,sql):
    df = pd.read_sql(sql, conn)
    print("inDb:",df.shape)
    return df

from pandas import DataFrame as df
def exe_sql_select(conn,sql):
    cur = conn.cursor() 
    data = None
    try: # 使用异常处理，以防程序无法正常运行
        cur.execute(sql) 
        data = df(cur.fetchall(), columns = [col[0] for col in cur.description]) 
    except Exception as e:
        conn.rollback() # 发生错误时回滚
        print('事务处理失败', e)
    else:
        # conn.commit() # 事务提交
        print('事务处理成功', cur.rowcount)
    # cur.close()
    return data

def selectlastDays(days=7):
    conn = pymysql.connect(**MYSQL_CONN_DBAPI)

    _selcolall = f''' `date`,`code`,`name`,`rate_1` '''
    _selcol = f'''  `date`,`code`,`name`,`rate_1` '''

    _table_name = 'cn_stock_strategy_enter'

    lastday = last_tddate(1)
    today_now = last_tddate(0)

    # sql = f'''SELECT '{_selcol}' FROM `{_table_name}` WHERE `date` = '{today_now}' and 
    #                                 `kdjk` >= 80 and `kdjd` >= 70 and `kdjj` >= 100 and `rsi_6` >= 80 and 
    #                                 `cci` >= 100 and `cr` >= 300 and `wr_6` >= -20 and `vr` >= 160'''

    # sql_now_price = f'''SELECT {_selcol} FROM `{_table_name}` WHERE `date` = '{lastday}' AND rate_1 > 0 '''

    if days == 0:

        # sql_now_today = f'''SELECT {_selcol} FROM `{_table_name}` WHERE `date` = '{today_now}' '''
        sql_now = f'''SELECT {_selcol} FROM `{_table_name}` WHERE `date` = '{today_now}' '''

    # sql_now_today = f'''SELECT {_selcol} FROM `{_table_name}` WHERE `date` = '{lastday}' '''

    else:
        # sql_now_last7day = f'''SELECT {_selcolall} FROM `{_table_name}` WHERE `date` >= '{last_tddate(days)}' '''
        sql_now = f'''SELECT {_selcolall} FROM `{_table_name}` WHERE `date` >= '{last_tddate(days)}' '''

    # sql_now_alltoday = f'''SELECT {_selcolall} FROM `{_table_name}`  '''

    # sql_tables_name =f'''select table_name from information_schema.tables where table_schema=`{db_database}` '''
    # # sql_columns = f'''select COLUMN_NAME from information_schema.COLUMNS where TABLE_SCHEMA=`{db_database}` and table_name = `{_table_name}`'''

    # sql_tables_name ='SHOW DATABASES'
    # # print('当前库下所有表的名称')
    # # sql_columns = "select COLUMN_NAME from information_schema.COLUMNS where table_name = '%s'"%(_table_name)
    # sql_columns = f'''select COLUMN_NAME from information_schema.COLUMNS where table_name = '{_table_name}' '''
    # print(sql_now_price)
    # print(sql_now_today)

    mycursor = conn.cursor()

    dflast = panda_df(conn,sql_now)
    # x = 0

    while len(dflast) == 0:
        for x in range(1, 20):
            # print(last_tddate(x))
            sql_now = f'''SELECT {_selcolall} FROM `{_table_name}` WHERE `date` >= '{last_tddate(x)}' '''
            dflast = panda_df(conn,sql_now)
            if len(dflast) > 5:
                break
    # mycursor.execute(sql_columns)
    # mycursor.execute(sql_now)

    # myresult = mycursor.fetchall()
    # for x in myresult:
    #   print(x)
    dflast['couts']=dflast.groupby(['code'])['code'].transform('count')
    conn.close()
    return dflast


def showcount(dflast7d,sort_date=False):

    df7multiIndex = dflast7d.reset_index().set_index(['code','date'])
    # print(df7multiIndex[:5])
    df7tail = df7multiIndex.groupby(level=[0]).tail(1)
    # df7tail.reset_index().code
    if sort_date:
        df7tail= df7tail.reset_index().sort_values(by=['date','rate_1'],ascending=[0,0])
    else:
        df7tail =  df7tail.sort_values(by=['rate_1'],ascending=[0])
    return (df7tail)

def show_macd_boll_up():
    conn = pymysql.connect(**MYSQL_CONN_DBAPI)


    lastday = last_tddate(1)
    today_now = last_tddate(0)

    mycursor = conn.cursor()

    sql_select_code = f'''select date,code,name,close,macd,macds,macdh,kdjk,kdjd,kdjj,boll_ub,boll FROM cn_stock_indicators WHERE macd>0 AND macds >0 AND macdh >0 AND close >=boll_ub AND date=CURDATE()  '''
    dflast = panda_df(conn,sql_select_code)
    # dflast = []
    while len(dflast) == 0:
        for x in range(1, 20):
            # print(last_tddate(x))
            # sql_now = f'''SELECT {_selcolall} FROM `{_table_name}` WHERE `date` >= '{last_tddate(x)}' '''
            sql_select_code_da = f'''select date,code,name,close,macd,macds,macdh,kdjk,kdjd,kdjj,boll_ub,boll FROM cn_stock_indicators WHERE macd>0 AND macds >0 AND macdh >0 AND close >=boll_ub AND date=CURRENT_DATE - INTERVAL %s DAY  '''%(x)
            dflast = panda_df(conn,sql_select_code_da)
            if len(dflast) > 3:
                break
    # mycursor.execute(sql_columns)
    # mycursor.execute(sql_now)

    # myresult = mycursor.fetchall()
    # for x in myresult:
    #   print(x)
    conn.close()
    return dflast

def show_macd_boll():
    conn = pymysql.connect(**MYSQL_CONN_DBAPI)


    lastday = last_tddate(1)
    today_now = last_tddate(0)

    mycursor = conn.cursor()

    sql_select_code = f'''select date,code,name,close,macd,macds,macdh,kdjk,kdjd,kdjj,boll_ub,boll FROM cn_stock_indicators WHERE macd>0 AND macds >0 AND macdh >0 AND close >boll   AND date=CURDATE()  '''
    # sql_select_code = f'''select date,code,name,close,macd,macds,macdh,kdjk,kdjd,kdjj,boll_ub,boll FROM cn_stock_indicators WHERE macd>0 AND macds >0 AND macdh >0 AND close >boll   AND date >=CURRENT_DATE - INTERVAL 3 DAY '''
    
    dflast = panda_df(conn,sql_select_code)
    # dflast = []
    while len(dflast) == 0:
        for x in range(1, 20):
            # print(last_tddate(x))
            # sql_now = f'''SELECT {_selcolall} FROM `{_table_name}` WHERE `date` >= '{last_tddate(x)}' '''
            sql_select_code_da = f'''select date,code,name,close,macd,macds,macdh,kdjk,kdjd,kdjj,boll_ub,boll FROM cn_stock_indicators WHERE macd>0 AND macds >0 AND macdh >0 AND close >boll AND date=CURRENT_DATE - INTERVAL %s DAY  '''%(x)
            dflast = panda_df(conn,sql_select_code_da)
            if len(dflast) > 3:
                break
    # mycursor.execute(sql_columns)
    # mycursor.execute(sql_now)

    # myresult = mycursor.fetchall()
    # for x in myresult:
    #   print(x)
    conn.close()
    return dflast
def show_macd_boll_up7():
    conn = pymysql.connect(**MYSQL_CONN_DBAPI)


    lastday = last_tddate(1)
    today_now = last_tddate(0)

    mycursor = conn.cursor()

    sql_select_code = f'''select date,code,name,close,macd,macds,macdh,kdjk,kdjd,kdjj,boll_ub,boll FROM cn_stock_indicators WHERE macd>0 AND macds >0 AND macdh >0 AND date>=CURRENT_DATE - INTERVAL 7 DAY AND close >=boll_ub '''
    dd = panda_df(conn,sql_select_code)
    # dflast = []
    while len(dd) == 0:
        for x in range(1, 20):
            # print(last_tddate(x))
            # sql_now = f'''SELECT {_selcolall} FROM `{_table_name}` WHERE `date` >= '{last_tddate(x)}' '''
            sql_select_code_da = f'''select date,code,name,close,macd,macds,macdh,kdjk,kdjd,kdjj,boll_ub,boll FROM cn_stock_indicators WHERE macd>0 AND macds >0 AND macdh >0 AND date=CURRENT_DATE - INTERVAL %s DAY AND close >=boll_ub '''%(x)
            dd = panda_df(conn,sql_select_code_da)
            if len(dd) > 3:
                break
    # mycursor.execute(sql_columns)
    # mycursor.execute(sql_now)

    # myresult = mycursor.fetchall()
    # for x in myresult:
    #   print(x)
    conn.close()
    dd['couts'] = dd.groupby(['code'])['code'].transform('count')

    dd.date=dd.date.apply(lambda x:str(x))

    if len(dd[(dd.couts > 1) & (dd.date>=today_now)]) == 0:
        dd = dd[(dd.couts > 1) & (dd.date>=lastday)]
    else:
        dd = dd[(dd.couts > 1) & (dd.date>=today_now)]
    return dd

def show_stock_pattern(filter=True):
    conn = pymysql.connect(**MYSQL_CONN_DBAPI)


    lastday = last_tddate(1)
    today_now = last_tddate(0)

    mycursor = conn.cursor()

    # sql_select_code = f'''select date,code,name,closing_marubozu,marubozu,long_line_candle FROM cn_stock_pattern WHERE (closing_marubozu=100 OR marubozu=100 OR long_line_candle=100) AND date>CURDATE() - INTERVAL 7 DAY ORDER BY date desc ;'''
    sql_select_code = f'''select date,code,name,closing_marubozu,marubozu,long_line_candle FROM cn_stock_pattern WHERE (closing_marubozu=100) AND date>CURDATE() - INTERVAL 7 DAY ORDER BY date desc ;'''
    dd = panda_df(conn,sql_select_code)

    # while len(dd) == 0:
    #     for x in range(1, 7):
    #         # print(last_tddate(x))
    #         # sql_now = f'''SELECT {_selcolall} FROM `{_table_name}` WHERE `date` >= '{last_tddate(x)}' '''
    #         sql_select_code_da = f'''select date,code,name,close,macd,macds,macdh,kdjk,kdjd,kdjj,boll_ub,boll FROM cn_stock_indicators WHERE macd>0 AND macds >0 AND macdh >0 AND date=CURRENT_DATE - INTERVAL %s DAY AND close >=boll_ub '''%(x)
    #         dd = panda_df(conn,sql_select_code_da)
    #         if len(dflast) > 0:
    #             break

    # mycursor.execute(sql_columns)
    # mycursor.execute(sql_now)

    # myresult = mycursor.fetchall()
    # for x in myresult:
    #   print(x)
    conn.close()
    dd['couts'] = dd.groupby(['code'])['code'].transform('count')

    dd.date=dd.date.apply(lambda x:str(x))
    dd = dd.sort_values(by=['couts'],ascending=[0])
    if len(dd[(dd.couts > 1) & (dd.date>=today_now)]) == 0:
        dd = dd[((dd.couts > 1)  | ((dd.marubozu == 100) & (dd.long_line_candle == 100)) ) & (dd.date>=lastday) ]
    else:
        dd = dd[((dd.couts > 1)  | ((dd.marubozu == 100) & (dd.long_line_candle == 100)) ) & (dd.date>=today_now) ]
    
    
    # if len(dd[dd.couts > dd.couts.mean()]) > 0:

    #     dd = dd[dd.couts > dd.couts.mean()]
    # else:
    #     dd = dd[dd.couts > dd.couts.mean()]

    if filter:
        df_boll = show_macd_boll_up()
        colist = [co for co in dd.code.values if co in df_boll.code.values]

        return dd.set_index('code').loc[colist].reset_index()
    else:
        return dd

if __name__ == '__main__':
    # print(selectlastDays(7)[selectlastDays(7).code == '600355'])
    # print(selectlastDays(0))

    # print(showcount(selectlastDays(1),sort_date=True))

    showcount(selectlastDays(14),sort_date=True)
    # import ipdb;ipdb.set_trace()
    # df = show_macd_boll()
    print(df[:10])
    print(show_macd_boll_up())
    print(show_macd_boll_up7())
    df=show_stock_pattern()
    print(df)
    # blkname = '066.blk'
    # block_path = tdd.get_tdx_dir_blocknew() + blkname
    # cct.write_to_blocknew(block_path, df.code.tolist(),append=False,doubleFile=False,keep_last=0,dfcf=False)