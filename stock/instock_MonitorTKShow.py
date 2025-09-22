# -*- coding:utf-8 -*-
import os
import gc
import sys
import time
import json
import threading
import multiprocessing as mp
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd

from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import LoggerFactory, commonTips as cct
from JSONData import stockFilter as stf
from JSONData import tdx_data_Day as tdd

log = LoggerFactory.log
# log.setLevel(log_level)
# log.setLevel(LoggerFactory.DEBUG)
# log.setLevel(LoggerFactory.INFO)
# -------------------- 常量 -------------------- #
DISPLAY_COLS = ct.get_Duration_format_Values(
    ct.Monitor_format_trade,
    ['name','trade','boll','dff','df2','couts','percent','volume','category']
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DARACSV_DIR = os.path.join(BASE_DIR, "datacsv")
WINDOW_CONFIG_FILE = os.path.join(BASE_DIR, "window_config.json")
SEARCH_HISTORY_FILE = os.path.join(DARACSV_DIR, "search_history.json")
os.makedirs(DARACSV_DIR, exist_ok=True)
START_INIT = 0
st_key_sort = '3 0'



# ------------------ 后台数据进程 ------------------ #
def fetch_and_process(shared_dict,queue, blkname="boll", flag=None):
    global st_key_sort,START_INIT
    g_values = cct.GlobalValues(shared_dict)  # 主进程唯一实例
    resample = g_values.getkey("resample") or "d"
    market = g_values.getkey("market", "all")        # all / sh / cyb / kcb / bj
    blkname = g_values.getkey("blkname", "061.blk")  # 对应的 blk 文件
    print(f"当前选择市场: {market}, blkname={blkname}")

    market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(st_key_sort)
    lastpTDX_DF, top_all = pd.DataFrame(), pd.DataFrame()
    print(f"init resample: {resample} flag.value : {flag.value}")
    while True:
        print(f'resample : new : {g_values.getkey("resample")} last : {resample} ')
        if flag is not None and not flag.value:   # 停止刷新
               time.sleep(1)
               print(f'flag.value : {flag.value} 停止更新')
               continue
        elif g_values.getkey("resample") and  g_values.getkey("resample") !=  resample:
            print(f'resample : new : {g_values.getkey("resample")} last : {resample} ')
            top_all = pd.DataFrame()
            lastpTDX_DF = pd.DataFrame()
        elif g_values.getkey("market") and  g_values.getkey("market") !=  market:
            print(f'market : new : {g_values.getkey("market")} last : {market} ')
            top_all = pd.DataFrame()
            lastpTDX_DF = pd.DataFrame()
        elif (not cct.get_work_time()) and START_INIT > 0:
                print(f'not worktime and work_duration')
                time.sleep(5)
                continue
        else:
            print(f'start worktime and work_duration get_work_time: {cct.get_work_time()} , START_INIT :{START_INIT} ')
        try:
            # resample = cct.GlobalValues().getkey("resample") or "d"
            resample = g_values.getkey("resample") or "d"
            market = g_values.getkey("market", "all")        # all / sh / cyb / kcb / bj
            blkname = g_values.getkey("blkname", "061.blk")  # 对应的 blk 文件
            print(f"resample: {resample} flag.value : {flag.value}")
            top_now = tdd.getSinaAlldf(market=market,vol=ct.json_countVol, vtype=ct.json_countType)
            if top_now.empty:
                log.debug("no data fetched")
                time.sleep(ct.duration_sleep_time)
                continue

            if top_all.empty:
                if lastpTDX_DF.empty:
                    top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl= ct.Resample_LABELS_Days[resample], resample=resample)
                else:
                    top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF)
            else:
                top_all = cct.combine_dataFrame(top_all, top_now, col="couts", compare="dff")

            top_all = calc_indicators(top_all, resample)

            sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort)

            top_temp = top_all.copy()
            if blkname == "boll":
                if "market_value" in top_temp.columns:
                    top_temp = top_temp.dropna(subset=["market_value"])
                    top_temp["market_value"] = top_temp["market_value"].fillna("0")
                    top_temp = top_temp[top_temp["market_value"].apply(lambda x: str(x).replace('.','',1).isdigit())]
                top_temp = stf.getBollFilter(df=top_temp, resample=resample, down=True)
                if top_temp is None:
                    top_temp = pd.DataFrame(columns=DISPLAY_COLS)

            top_temp = top_temp.sort_values(by=sort_cols, ascending=sort_keys)
            top_temp = top_temp.loc[:, DISPLAY_COLS]

            queue.put(top_temp)
            gc.collect()
            time.sleep(ct.duration_sleep_time)
            START_INIT = 1
            print(f'START_INIT : {START_INIT} fetch_and_process sleep:{ct.duration_sleep_time} resample:{resample}')
            # log.debug(f'fetch_and_process timesleep:{ct.duration_sleep_time} resample:{resample}')
        except Exception as e:
            log.error(f"Error in background process: {e}", exc_info=True)
            time.sleep(ct.duration_sleep_time / 2)

# ------------------ 指标计算 ------------------ #
def calc_indicators(top_all, resample):
    if cct.get_trade_date_status() == 'True':
        for co in ['boll', 'df2']:
            top_all[co] = list(
                map(lambda x, y, m, z: z + (1 if (x > y) else 0),
                    top_all.close.values,
                    top_all.upper.values,
                    top_all.llastp.values,
                    top_all[co].values)
            )
    top_all = top_all[(top_all.df2 > 0) & (top_all.boll > 0)]
    ratio_t = cct.get_work_time_ratio(resample=resample)
    top_all['volume'] = list(
        map(lambda x, y: round(x / y / ratio_t, 1),
            top_all['volume'].values,
            top_all.last6vol.values)
    )
    now_time = cct.get_now_time_int()
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
        top_all['dff'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
    return top_all.sort_values(by=['dff','percent','volume','ratio','couts'], ascending=[0,0,0,1,1])

# ------------------ Tk 前端 ------------------ #
# class StockMonitorApp(tk.Tk):
#     def __init__(self, queue):
#         super().__init__()
#         self.queue = queue
#         self.title("Stock Monitor")
#         self.load_window_position()

#         # ----------------- 控件框 ----------------- #
#         ctrl_frame = tk.Frame(self)
#         ctrl_frame.pack(fill="x", padx=5, pady=2)

#         tk.Label(ctrl_frame, text="blkname:").pack(side="left")
#         self.blk_label = tk.Label(ctrl_frame, text=cct.GlobalValues().getkey("blkname") or "boll")
#         self.blk_label.pack(side="left", padx=2)

#         tk.Label(ctrl_frame, text="resample:").pack(side="left", padx=5)
#         self.resample_combo = ttk.Combobox(ctrl_frame, values=["d","w","m"], width=5)
#         self.resample_combo.set(cct.GlobalValues().getkey("resample") or "d")
#         self.resample_combo.pack(side="left")
#         self.resample_combo.bind("<<ComboboxSelected>>", self.set_resample)

#         tk.Label(ctrl_frame, text="Search:").pack(side="left", padx=5)
#         self.search_entry = tk.Entry(ctrl_frame, width=30)
#         self.search_entry.pack(side="left", padx=2)
#         tk.Button(ctrl_frame, text="Go", command=self.set_search).pack(side="left", padx=2)

#         # 数据存档按钮
#         tk.Button(ctrl_frame, text="保存数据", command=self.save_data_to_csv).pack(side="left", padx=2)
#         tk.Button(ctrl_frame, text="读取存档", command=self.load_data_from_csv).pack(side="left", padx=2)

#         # ----------------- 状态栏 ----------------- #
#         self.status_var = tk.StringVar()
#         self.status_bar = tk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
#         self.status_bar.pack(fill="x", side="bottom")

#         # ----------------- TreeView ----------------- #
#         tree_frame = tk.Frame(self)
#         tree_frame.pack(fill="both", expand=True)
#         self.tree = ttk.Treeview(tree_frame, columns=["code"] + DISPLAY_COLS, show="headings")
#         vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
#         hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
#         self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
#         vsb.pack(side="right", fill="y")
#         hsb.pack(side="bottom", fill="x")
#         self.tree.pack(fill="both", expand=True)

#         # checkbuttons 顶部右侧
#         self.init_checkbuttons(ctrl_frame)

#         # TreeView 列头
#         for col in ["code"] + DISPLAY_COLS:
#             width = 120 if col=="name" else 80
#             self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
#             self.tree.column(col, width=width, anchor="center", minwidth=50)

#         self.current_df = pd.DataFrame()
#         self.after(500, self.update_tree)
#         self.protocol("WM_DELETE_WINDOW", self.on_close)
#         # Tree selection event
#         self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
#         self.sender = StockSender(self.tdx_var, self.ths_var, self.dfcf_var, callback=self.update_send_status)
class StockMonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        # self.queue = queue
        self.title("Stock Monitor")
        self.load_window_position()

        # 刷新开关标志
        self.refresh_enabled = True
        from multiprocessing import Manager
        manager = Manager()
        self.global_dict = manager.dict()  # 共享字典
        self.global_dict["resample"] = "d"
        self.global_values = cct.GlobalValues(self.global_dict)
        resample = self.global_values.getkey("resample")
        print(f'app init getkey resample:{self.global_values.getkey("resample")}')
        self.global_values.setkey("resample", resample)

        # ----------------- 控件框 ----------------- #
        ctrl_frame = tk.Frame(self)
        ctrl_frame.pack(fill="x", padx=5, pady=2)

        # tk.Label(ctrl_frame, text="blkname:").pack(side="left")
        # self.blk_label = tk.Label(ctrl_frame, text=cct.GlobalValues().getkey("blkname") or "boll")
        # self.blk_label.pack(side="left", padx=2)

        # tk.Label(ctrl_frame, text="resample:").pack(side="left", padx=5)
        # self.resample_combo = ttk.Combobox(ctrl_frame, values=["d","w","m"], width=5)
        # self.resample_combo.set(cct.GlobalValues().getkey("resample") or "d")
        # self.resample_combo.pack(side="left")
        # self.resample_combo.bind("<<ComboboxSelected>>", self.set_resample)

        # tk.Label(ctrl_frame, text="Search:").pack(side="left", padx=5)
        # self.search_entry = tk.Entry(ctrl_frame, width=30)
        # self.search_entry.pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="Go", command=self.set_search).pack(side="left", padx=2)

        # # 数据存档按钮
        # tk.Button(ctrl_frame, text="保存数据", command=self.save_data_to_csv).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="读取存档", command=self.load_data_from_csv).pack(side="left", padx=2)

        # # 刷新控制按钮
        # tk.Button(ctrl_frame, text="停止刷新", command=self.stop_refresh).pack(side="left", padx=5)
        # tk.Button(ctrl_frame, text="启动刷新", command=self.start_refresh).pack(side="left", padx=2)

        # ----------------- 状态栏 ----------------- #
        self.status_var = tk.StringVar()
        self.status_bar = tk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_bar.pack(fill="x", side="bottom")

        # ----------------- TreeView ----------------- #
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=["code"] + DISPLAY_COLS, show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # TreeView 列头
        for col in ["code"] + DISPLAY_COLS:
            width = 120 if col=="name" else 80
            self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
            self.tree.column(col, width=width, anchor="center", minwidth=50)

        self.current_df = pd.DataFrame()

        # 队列接收子进程数据
        self.queue = mp.Queue()

        # UI 构建
        self._build_ui(ctrl_frame)

        # checkbuttons 顶部右侧
        self.init_checkbuttons(ctrl_frame)
        # 启动后台进程
        self._start_process()

        # 定时检查队列
        self.after(1000, self.update_tree)


        self.protocol("WM_DELETE_WINDOW", self.on_close)
        # Tree selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.sender = StockSender(self.tdx_var, self.ths_var, self.dfcf_var, callback=self.update_send_status)

    def _build_ui(self, ctrl_frame):

        # Market 下拉菜单
        tk.Label(ctrl_frame, text="Market:").pack(side="left", padx=5)

        # 显示值和内部值的映射
        # self.market_map = {
        #     "全部": "all",
        #     "上证": "sh",
        #     "创业板": "cyb",
        #     "科创板": "kcb",
        #     "北证": "bj",
        # }
        # self.market_combo = ttk.Combobox(
        #     ctrl_frame,
        #     values=list(self.market_map.keys()),  # 显示中文
        #     width=8,
        #     state="readonly"
        # )
        # self.market_combo.current(0)  # 默认 "全部"
        # self.market_combo.pack(side="left", padx=5)
        # # 绑定选择事件，选中后保存到 GlobalValues
        # def on_market_select(event=None):
        #     market_cn = self.market_combo.get()
        #     market_code = self.market_map.get(market_cn, "all")
        #     self.global_dict.setkey("market", market_code)
                # Market 下拉菜单

        # 显示中文 → 内部 code + blkname
        self.market_map = {
            "全部": {"code": "all", "blkname": "061.blk"},
            "上证": {"code": "sh",  "blkname": "062.blk"},
            "创业板": {"code": "cyb", "blkname": "063.blk"},
            "科创板": {"code": "kcb", "blkname": "064.blk"},
            "北证": {"code": "bj",  "blkname": "065.blk"},
        }

        self.market_combo = ttk.Combobox(
            ctrl_frame,
            values=list(self.market_map.keys()),  # 显示中文
            width=8,
            state="readonly"
        )
        self.market_combo.current(0)  # 默认 "全部"
        self.market_combo.pack(side="left", padx=5)

        # 绑定选择事件，存入 GlobalValues
        def on_market_select(event=None):
            market_cn = self.market_combo.get()
            market_info = self.market_map.get(market_cn, {"code": "all", "blkname": "061.blk"})
            self.global_values.setkey("market", market_info["code"])
            self.global_values.setkey("blkname", market_info["blkname"])
            print(f"选择市场: {market_cn}, code={market_info['code']}, blkname={market_info['blkname']}")

        self.market_combo.bind("<<ComboboxSelected>>", on_market_select)

        # 控件区
        tk.Label(ctrl_frame, text="blk:").pack(side="left")
        self.blk_label = tk.Label(ctrl_frame, text=self.global_values.getkey("blkname") or "061.blk")
        self.blk_label.pack(side="left", padx=2)


        # --- resample 下拉框 ---
        tk.Label(ctrl_frame, text="Resample:").pack(side="left")
        self.resample_combo = ttk.Combobox(ctrl_frame, values=["d",'3d', "w", "m"], width=5)
        self.resample_combo.current(0)
        self.resample_combo.pack(side="left", padx=5)
        self.resample_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())
        # --- 刷新按钮 ---
        tk.Button(ctrl_frame, text="刷新", command=self.refresh_data).pack(side="left", padx=5)

        # --- 搜索框 ---
        # tk.Label(ctrl_frame, text="搜索:").pack(side="left")
        # self.search_var = tk.StringVar()
        # self.search_entry = tk.Entry(ctrl_frame, textvariable=self.search_var)
        # self.search_entry.pack(side="left", padx=5)
        # self.search_entry.bind("<Return>", lambda e: self.set_search())

        # 在 __init__ 中
        self.search_history = self.load_search_history()
        self.search_var = tk.StringVar()
        self.search_combo = ttk.Combobox(ctrl_frame, textvariable=self.search_var, values=self.search_history, width=30)
        self.search_combo.pack(side="left", padx=5)
        self.search_combo.bind("<Return>", lambda e: self.apply_search())
        self.search_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_search())  # 选中历史也刷新
        tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="删除历史", command=self.delete_search_history).pack(side="left", padx=2)

        # --- 数据存档按钮 ---
        tk.Button(ctrl_frame, text="保存数据", command=self.save_data_to_csv).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="读取存档", command=self.load_data_from_csv).pack(side="left", padx=2)

        # --- 刷新控制按钮 ---
        tk.Button(ctrl_frame, text="停止刷新", command=self.stop_refresh).pack(side="left", padx=5)
        tk.Button(ctrl_frame, text="启动刷新", command=self.start_refresh).pack(side="left", padx=2)

    # def _build_ui(self,ctrl_frame):
    #     # 控件区

    #     # ctrl_frame = tk.Frame(self)
    #     # ctrl_frame.pack(side="top", fill="x")
    #     tk.Label(ctrl_frame, text="blkname:").pack(side="left")
    #     self.blk_label = tk.Label(ctrl_frame, text=cct.GlobalValues().getkey("blkname") or "boll")
    #     self.blk_label.pack(side="left", padx=2)

    #     # --- resample 下拉框 ---
    #     tk.Label(ctrl_frame, text="Resample:").pack(side="left")
    #     self.resample_combo = ttk.Combobox(ctrl_frame, values=["d", "w", "m"], width=5)
    #     self.resample_combo.current(0)
    #     self.resample_combo.pack(side="left", padx=5)

    #     # --- 刷新按钮（新增） ---
    #     tk.Button(ctrl_frame, text="刷新", command=self.refresh_data).pack(side="left", padx=5)

    #     # --- 搜索框 ---
    #     tk.Label(ctrl_frame, text="搜索:").pack(side="left")
    #     self.search_var = tk.StringVar()
    #     self.search_entry = tk.Entry(ctrl_frame, textvariable=self.search_var)
    #     self.search_entry.pack(side="left", padx=5)
    #     # self.search_entry.bind("<Return>", lambda e: self.apply_search())
    #     self.search_entry.bind("<Return>", lambda e: self.set_search())
    #     tk.Button(ctrl_frame, text="Go", command=self.set_search).pack(side="left", padx=2)

    #     # tk.Label(ctrl_frame, text="Search:").pack(side="left", padx=5)
    #     # self.search_entry = tk.Entry(ctrl_frame, width=30)
    #     # self.search_entry.pack(side="left", padx=2)
    #     # tk.Button(ctrl_frame, text="Go", command=self.set_search).pack(side="left", padx=2)

    #     # # TreeView  重复创建了
    #     # self.tree = ttk.Treeview(self, show="headings")
    #     # self.tree.pack(side="top", fill="both", expand=True)

    #     # 状态栏
    #     self.status_var = tk.StringVar(value="初始化完成")
    #     status_bar = tk.Label(self, textvariable=self.status_var, anchor="w")
    #     status_bar.pack(side="bottom", fill="x")

    #             # 数据存档按钮
    #     tk.Button(ctrl_frame, text="保存数据", command=self.save_data_to_csv).pack(side="left", padx=2)
    #     tk.Button(ctrl_frame, text="读取存档", command=self.load_data_from_csv).pack(side="left", padx=2)

    #     # 刷新控制按钮
    #     tk.Button(ctrl_frame, text="停止刷新", command=self.stop_refresh).pack(side="left", padx=5)
    #     tk.Button(ctrl_frame, text="启动刷新", command=self.start_refresh).pack(side="left", padx=2)

    def refresh_data(self):
        """
        手动刷新：更新 resample 全局配置，触发后台进程下一轮 fetch_and_process
        """
        resample = self.resample_combo.get().strip()
        print(f'set resample : {resample}')
        # cct.GlobalValues().setkey("resample", resample)
        self.global_values.setkey("resample", resample)
        self.status_var.set(f"手动刷新: resample={resample}")

    def _start_process(self):
        self.refresh_flag = mp.Value('b', True)
        # self.proc = mp.Process(target=fetch_and_process, args=(self.queue,))
        self.proc = mp.Process(target=fetch_and_process, args=(self.global_dict,self.queue, "boll", self.refresh_flag))
        # self.proc.daemon = True
        self.proc.daemon = False 
        self.proc.start()

    # def update_tree(self):
    #     try:
    #         while not self.queue.empty():
    #             df = self.queue.get_nowait()
    #             self.refresh_tree(df)
    #             self.status_var.set(f"刷新完成: 共 {len(df)} 行数据")
    #     except Exception as e:
    #         LoggerFactory.log.error(f"Error updating tree: {e}", exc_info=True)
    #     finally:
    #         self.after(1000, self.update_tree)

    # def refresh_tree(self, df):
    #     # 清理旧数据
    #     for col in self.tree["columns"]:
    #         self.tree.heading(col, text="")
    #     self.tree.delete(*self.tree.get_children())

    #     if df.empty:
    #         return

    #     # 重新加载表头
    #     self.tree["columns"] = list(df.columns)
    #     for col in df.columns:
    #         self.tree.heading(col, text=col)

    #     # 插入数据
    #     for idx, row in df.iterrows():
    #         self.tree.insert("", "end", values=list(row))

    # def apply_search(self):
        # query = self.search_var.get().strip()
        # if not query:
        #     self.status_var.set("搜索框为空")
        #     return
        # self.status_var.set(f"搜索: {query}")

    # # ----------------- 启停刷新 ----------------- #
    # def stop_refresh(self):
    #     self.refresh_enabled = False
    #     self.status_var.set("刷新已停止")

    # def start_refresh(self):
    #     self.refresh_enabled = True
    #     self.status_var.set("刷新已启动")
    def stop_refresh(self):
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = False
            print(f'refresh_flag.value : {self.refresh_flag.value}')
        self.status_var.set("刷新已停止")

    def start_refresh(self):
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = True
            print(f'refresh_flag.value : {self.refresh_flag.value}')
        self.status_var.set("刷新已启动")


    # ----------------- 数据刷新 ----------------- #
    def update_tree(self):
        try:
            if self.refresh_enabled:  # ✅ 只在启用时刷新
                while not self.queue.empty():
                    df = self.queue.get_nowait()
                    log.info(f'df:{df[:1]}')
                    self.refresh_tree(df)
        except Exception as e:
            log.error(f"Error updating tree: {e}", exc_info=True)
        finally:
            self.after(1000, self.update_tree)

    def on_tree_select(self, event):
        selected_item = self.tree.selection()
        if selected_item:
            stock_info = self.tree.item(selected_item, 'values')
            stock_code = stock_info[0]
            stock_code = str(stock_code).zfill(6)
            log.info(f'stock_code:{stock_code}')
            # send_to_tdx(stock_code)   # 根据你的逻辑发送到 TDX 或其他
            print(f"选中股票代码: {stock_code}")
            if stock_code:
                self.sender.send(stock_code)

    def update_send_status(self, status_dict):
        # 更新状态栏
        status_text = f"TDX: {status_dict['TDX']} | THS: {status_dict['THS']} | DC: {status_dict['DC']}"
        self.status_var.set(status_text)

    # ----------------- Checkbuttons ----------------- #
    def init_checkbuttons(self, parent_frame):
        frame_right = tk.Frame(parent_frame, bg="#f0f0f0")
        frame_right.pack(side=tk.RIGHT, padx=2, pady=2)

        self.tdx_var = tk.BooleanVar(value=True)
        self.ths_var = tk.BooleanVar(value=False)
        self.dfcf_var = tk.BooleanVar(value=False)
        self.uniq_var = tk.BooleanVar(value=False)
        self.sub_var = tk.BooleanVar(value=False)

        checkbuttons_info = [
            ("TDX", self.tdx_var),
            ("THS", self.ths_var),
            ("DC", self.dfcf_var),
            ("Uniq", self.uniq_var),
            ("Sub", self.sub_var)
        ]
        for text, var in checkbuttons_info:
            cb = tk.Checkbutton(frame_right, text=text, variable=var, command=self.update_linkage_status,
                                bg="#f0f0f0", font=('Microsoft YaHei', 9),
                                padx=0, pady=0, bd=0, highlightthickness=0)
            cb.pack(side=tk.LEFT, padx=1)

    def update_linkage_status(self):
        # 此处处理 checkbuttons 状态
        if not self.tdx_var.get() or self.ths_var.get() or self.dfcf_var.get():
            self.sender.reload()
        print(f"TDX:{self.tdx_var.get()}, THS:{self.ths_var.get()}, DC:{self.dfcf_var.get()}, Uniq:{self.uniq_var.get()}, Sub:{self.sub_var.get()}")

    # def refresh_tree(self, df):
    #     for i in self.tree.get_children():
    #         self.tree.delete(i)
    #     log.debug(f'refresh_tree df:{df[:2]}')
    #     if not df.empty:
    #         df = df.copy()
    #         # 检查 DISPLAY_COLS 中 code 是否已经存在
    #         if 'code' not in df.columns:
    #             df.insert(0, "code", df.index)
    #         # 如果 df 已经有 code，确保列顺序和 DISPLAY_COLS 一致
    #         cols_to_show = ['code'] + [c for c in DISPLAY_COLS if c != 'code']
    #         df = df.reindex(columns=cols_to_show)
    #         # 插入到 TreeView
    #         for _, row in df.iterrows():
    #             self.tree.insert("", "end", values=list(row))
    #     self.current_df = df
    #     self.adjust_column_widths()
    #     self.update_status()
    def refresh_tree(self, df):
        for i in self.tree.get_children():
            self.tree.delete(i)

        if df.empty:
            self.current_df = df
            self.update_status()
            return

        df = df.copy()
        # 确保 code 列存在
        if 'code' not in df.columns:
            df.insert(0, "code", df.index)
        cols_to_show = ['code'] + [c for c in DISPLAY_COLS if c != 'code']
        df = df.reindex(columns=cols_to_show)

        # 自动搜索过滤
        query = self.search_var.get().strip()
        if query:
            try:
                df = df.query(query)
            except Exception as e:
                log.error(f"自动搜索过滤错误: {e}")

        # 插入到 TreeView
        for _, row in df.iterrows():
            self.tree.insert("", "end", values=list(row))

        self.current_df = df
        self.adjust_column_widths()
        self.update_status()


    # ------------------ 调整列宽 ------------------ #
    # def adjust_column_widths(self):
    #     for col in DISPLAY_COLS:
    #         if col in self.current_df.columns:
    #             max_len = max([len(str(val)) for val in self.current_df[col]] + [len(col)])
    #             width = min(max(max_len * 10, 60), 300) 
    #             if col == 'name':
    #                 width =int(width * 1.8) 
    #             self.tree.column(col, width=width)

    def adjust_column_widths(self):
        # 只调整 Treeview 中存在的列
        for col in self.tree["columns"]:
            if col in self.current_df.columns:
                max_len = max([len(str(val)) for val in self.current_df[col]] + [len(col)])
                width = min(max(max_len * 10, 60), 300)
                if col == 'name':
                    width = int(width * 1.8)
                self.tree.column(col, width=width)


    # ----------------- 排序 ----------------- #
    def sort_by_column(self, col, reverse):
        if col in ['code'] or col not in self.current_df.columns:
            return
        df_sorted = self.current_df.sort_values(by=col, ascending=not reverse)
        self.refresh_tree(df_sorted)
        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))

    def save_search_history(self):
        try:
            with open(SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.search_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"保存搜索历史失败: {e}")

    def load_search_history(self):
        if os.path.exists(SEARCH_HISTORY_FILE):
            try:
                with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"加载搜索历史失败: {e}")
        return []

    def apply_search(self):
        query = self.search_var.get().strip()
        if not query:
            self.status_var.set("搜索框为空")
            return

        if query not in self.search_history:
            self.search_history.insert(0, query)
            if len(self.search_history) > 20:  # 最多保存20条
                self.search_history = self.search_history[:20]
            self.search_combo['values'] = self.search_history
            self.save_search_history()  # 保存到文件

        if self.current_df.empty:
            self.status_var.set("当前数据为空")
            return

        try:
            df_filtered = self.current_df.query(query)
            self.refresh_tree(df_filtered)
            self.status_var.set(f"搜索: {query} | 结果 {len(df_filtered)} 行")
        except Exception as e:
            log.error(f"Query error: {e}")
            self.status_var.set(f"查询错误: {e}")

    def clean_search(self, entry=None):
        """删除指定历史，默认删除当前搜索框内容"""
        self.search_var.set('')
        self.refresh_tree(self.current_df)
        resample = self.resample_combo.get()
        self.status_var.set(f"Row 结果 {len(self.current_df)} 行 | resample: {resample} ")
    
    def delete_search_history(self, entry=None):
        """删除指定历史，默认删除当前搜索框内容"""
        target = entry or self.search_var.get().strip()
        if target in self.search_history:
            self.search_history.remove(target)
            self.search_combo['values'] = self.search_history
            self.save_search_history()
            self.status_var.set(f"已删除历史: {target}")


    # ----------------- 搜索 ----------------- #
    # def set_search(self):
    #     query = self.search_entry.get().strip()
    #     if query and not self.current_df.empty:
    #         try:
    #             df_filtered = self.current_df.query(query)
    #             self.refresh_tree(df_filtered)
    #         except Exception as e:
    #             log.error(f"Query error: {e}")

    # # ----------------- Resample ----------------- #
    # def set_resample(self, event=None):
    #     val = self.resample_combo.get().strip()
    #     if val:
    #         cct.GlobalValues().setkey("resample", val)

    # ----------------- 状态栏 ----------------- #
    def update_status(self):
        cnt = len(self.current_df)
        blk = self.blk_label.cget("text")
        resample = self.resample_combo.get()
        # search = self.search_entry.get()
        search = self.search_var.get()
        self.status_var.set(f"Rows: {cnt} | blkname: {blk} | resample: {resample} | search: {search}")

    # ----------------- 数据刷新 ----------------- #
    # def update_tree(self):
    #     try:
    #         while not self.queue.empty():
    #             df = self.queue.get_nowait()
    #             log.debug(f'df:{df[:2]}')
    #             self.refresh_tree(df)
    #     except Exception as e:
    #         log.error(f"Error updating tree: {e}", exc_info=True)
    #     finally:
    #         self.after(1000, self.update_tree)

    # ----------------- 数据存档 ----------------- #
    def save_data_to_csv(self):
        if self.current_df.empty:
            return
        import datetime
        file_name = os.path.join(DARACSV_DIR, f"monitor_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        self.current_df.to_csv(file_name, index=True, encoding="utf-8-sig")
        self.status_var.set(f"已保存数据到 {file_name}")

    def load_data_from_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_path:
            try:
                df = pd.read_csv(file_path, index_col=0)
                # 如果 CSV 本身已经有 code 列，不要再插入
                if 'code' in df.columns:
                    df = df.copy()
                self.refresh_tree(df)
                self.status_var.set(f"已加载数据: {file_path}")
            except Exception as e:
                log.error(f"加载 CSV 失败: {e}")

    # ----------------- 窗口位置记忆 ----------------- #
    def save_window_position(self):
        pos = {"x": self.winfo_x(), "y": self.winfo_y(), "width": self.winfo_width(), "height": self.winfo_height()}
        try:
            with open(WINDOW_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(pos, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"保存窗口位置失败: {e}")

    def load_window_position(self):
        if os.path.exists(WINDOW_CONFIG_FILE):
            try:
                with open(WINDOW_CONFIG_FILE, "r", encoding="utf-8") as f:
                    pos = json.load(f)
                    self.geometry(f"{pos['width']}x{pos['height']}+{pos['x']}+{pos['y']}")
            except Exception as e:
                log.error(f"读取窗口位置失败: {e}")

    def on_close(self):
        self.save_window_position()
        self.save_search_history()
        self.destroy()

# ------------------ 主程序入口 ------------------ #
if __name__ == "__main__":
    cct.GlobalValues().setkey('resample','d')
    # queue = mp.Queue()
    # p = mp.Process(target=fetch_and_process, args=(queue,))
    # p.daemon = True
    # p.start()
    # app = StockMonitorApp(queue)

    # from multiprocessing import Manager
    # manager = Manager()
    # global_dict = manager.dict()  # 共享字典
    app = StockMonitorApp()
    app.mainloop()
