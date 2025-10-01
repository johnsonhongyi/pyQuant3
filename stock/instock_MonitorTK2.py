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
            # if blkname == "boll":
            #     if "market_value" in top_temp.columns:
            #         top_temp = top_temp.dropna(subset=["market_value"])
            #         top_temp["market_value"] = top_temp["market_value"].fillna("0")
            #         top_temp = top_temp[top_temp["market_value"].apply(lambda x: str(x).replace('.','',1).isdigit())]
            #     top_temp = stf.getBollFilter(df=top_temp, resample=resample, down=True)
            #     if top_temp is None:
            #         top_temp = pd.DataFrame(columns=DISPLAY_COLS)

            top_temp = top_temp.sort_values(by=sort_cols, ascending=sort_keys)
            # print(f'DISPLAY_COLS:{DISPLAY_COLS}')
            # print(f'col: {top_temp.columns.values}')
            # top_temp = top_temp.loc[:, DISPLAY_COLS]

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
    # top_all = top_all[(top_all.df2 > 0) & (top_all.boll > 0)]
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

from alerts_manager import AlertManager, open_alert_center, set_global_manager, check_alert

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

        self.df_all = pd.DataFrame()      # 保存 fetch_and_process 返回的完整原始数据
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

        # 在初始化时（StockMonitorApp.__init__）创建并注册：
        self.alert_manager = AlertManager(storage_dir=DARACSV_DIR, logger=log)
        set_global_manager(self.alert_manager)
        # 在 UI 控件区加个按钮：
        tk.Button(ctrl_frame, text="报警中心", command=lambda: open_alert_center(self)).pack(side="left", padx=2)


        # ========== 右键菜单 ==========
        self.tree_menu = tk.Menu(self, tearoff=0)
        self.tree_menu.add_command(label="打开报警中心", command=lambda: open_alert_center(self))
        self.tree_menu.add_command(label="新建报警规则", command=self.open_alert_rule_new)
        self.tree_menu.add_command(label="编辑报警规则", command=self.open_alert_rule_edit)

        # 绑定右键点击事件
        self.tree.bind("<Button-3>", self.on_tree_right_click)

    def open_alert_editorAuto(self, stock_info, new_rule=False):
        code = stock_info.get("code")
        name = stock_info.get("name")
        price = stock_info.get("price", 0.0)
        change = stock_info.get("change", 0.0)
        volume = stock_info.get("volume", 0)

        # 如果是新建规则，检查是否已有历史报警
        rules = self.alert_manager.get_rules(code)
        if new_rule or not rules:
            rules = [
                {"field": "价格", "op": ">=", "value": price, "enabled": True, "delta": 1},
                {"field": "涨幅", "op": ">=", "value": change, "enabled": True, "delta": 1},
                {"field": "量", "op": ">=", "value": volume, "enabled": True, "delta": 100}
            ]
            self.alert_manager.set_rules(code, rules)

        # 创建 Toplevel 编辑窗口，自动填充规则
        editor = tk.Toplevel(self)
        editor.title(f"设置报警规则 - {name} {code}")
        editor.geometry("500x300")
        editor.focus_force()
        editor.grab_set()

        # 创建规则 Frame 并渲染 rules
        # ...（这里可以复用你现有 add_rule、保存/删除按钮逻辑）


    def open_alert_editor(parent, stock_info=None, new_rule=True):
        """
        打开报警规则编辑窗口
        :param parent: 主窗口
        :param stock_info: 选中的股票信息 (tuple/list)，比如 (code, name, price, ...)
        :param new_rule: True=新建规则，False=编辑规则
        """
        win = tk.Toplevel(parent)
        win.title("新建报警规则" if new_rule else "编辑报警规则")
        win.geometry("400x300")

        # 如果 stock_info 有内容，在标题里显示
        stock_str = ""
        if stock_info:
            try:
                code, name = stock_info[0], stock_info[1]
                stock_str = f"{code} {name}"
            except Exception:
                stock_str = str(stock_info)
        if stock_str:
            tk.Label(win, text=f"股票: {stock_str}", font=("Arial", 12, "bold")).pack(pady=5)

        # 报警条件输入区
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(frame, text="条件类型:").grid(row=0, column=0, sticky="w")
        cond_type_var = tk.StringVar(value="价格大于")
        cond_type_entry = ttk.Combobox(frame, textvariable=cond_type_var,
                                       values=["价格大于", "价格小于", "涨幅超过", "跌幅超过"], state="readonly")
        cond_type_entry.grid(row=0, column=1, sticky="ew")

        tk.Label(frame, text="阈值:").grid(row=1, column=0, sticky="w")
        threshold_var = tk.StringVar(value="")
        threshold_entry = tk.Entry(frame, textvariable=threshold_var)
        threshold_entry.grid(row=1, column=1, sticky="ew")

        # 保存按钮
        def save_rule():
            rule = {
                "stock": stock_str,
                "cond_type": cond_type_var.get(),
                "threshold": threshold_var.get()
            }
            log.info(f"保存报警规则: {rule}")
            stock_code = rule.get("stock")  # 或者从 UI 里获取选中的股票代码
            print(f'stock_code:{stock_code}')
            import ipdb;ipdb.set_trace()
            parent.alert_manager.save_rule(stock_code['name'],rule)  # 保存到 AlertManager
            messagebox.showinfo("成功", "规则已保存")
            win.destroy()

        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", pady=10)
        tk.Button(btn_frame, text="保存", command=save_rule).pack(side="left", padx=5)
        tk.Button(btn_frame, text="取消", command=win.destroy).pack(side="left", padx=5)

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
        self.resample_combo = ttk.Combobox(ctrl_frame, values=["d",'3d', "w", "m"], width=3)
        self.resample_combo.current(0)
        self.resample_combo.pack(side="left", padx=5)
        self.resample_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())
        # --- 刷新按钮 ---
        # tk.Button(ctrl_frame, text="刷新", command=self.refresh_data).pack(side="left", padx=5)

        # --- 搜索框 ---
        # tk.Label(ctrl_frame, text="搜索:").pack(side="left")
        # self.search_var = tk.StringVar()
        # self.search_entry = tk.Entry(ctrl_frame, textvariable=self.search_var)
        # self.search_entry.pack(side="left", padx=5)
        # self.search_entry.bind("<Return>", lambda e: self.set_search())

        # 在 __init__ 中
        self.search_history = self.load_search_history()
        self.search_var = tk.StringVar()
        self.search_combo = ttk.Combobox(ctrl_frame, textvariable=self.search_var, values=self.search_history, width=20)
        self.search_combo.pack(side="left", padx=5)
        self.search_combo.bind("<Return>", lambda e: self.apply_search())
        self.search_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_search())  # 选中历史也刷新
        tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="删除历史", command=self.delete_search_history).pack(side="left", padx=2)

        # 查询输入框
        # self.query_var = tk.StringVar()
        # tk.Entry(ctrl_frame, textvariable=self.query_var, width=30).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="查询", command=self.on_query).pack(side="left", padx=2)

        # self.query_history = []  # [{'name':'中信','trade':'>=10','desc':'高成交股'}, ...]
        # self.query_combo_var = tk.StringVar()
        # self.query_combo = ttk.Combobox(ctrl_frame, textvariable=self.query_combo_var, width=15)
        # self.query_combo.pack(side="left", padx=2)
        # # self.update_query_combo()
        # self.query_combo.bind("<Return>", lambda e: self.on_query())
        # self.query_combo.bind("<<ComboboxSelected>>",  lambda e: self.on_query_select())

        # 当前查询说明标签
        # self.query_desc_label = tk.Label(ctrl_frame, text="", fg="blue")
        # self.query_desc_label.pack(side="left", padx=5)


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
                    self.df_all = df.copy()
                    self.refresh_tree(df)
        except Exception as e:
            log.error(f"Error updating tree: {e}", exc_info=True)
        finally:
            self.after(1000, self.update_tree)

    def on_tree_right_click(self, event):
        """右键点击 TreeView 行"""
        # 确保选中行
        item_id = self.tree.identify_row(event.y)
        if item_id:
          self.tree.selection_set(item_id)
          self.tree_menu.post(event.x_root, event.y_root)

    def open_alert_rule_new(self):
        """新建报警规则"""
        stock_info = getattr(self, "selected_stock_info", None)

        if not stock_info:
            auto_close_message("提示", "请先选择一个股票！")
            return
        
        # new_rule=True 表示创建新规则
        self.open_alert_editor(stock_info=stock_info, new_rule=True)

    def open_alert_rule_edit(self):
        """编辑报警规则"""
        stock_info = getattr(self, "selected_stock_info", None)

        if not stock_info:
            messagebox.showwarning("提示", "请先选择一只股票")
            return
        self.open_alert_editor(self, stock_info=stock_info, new_rule=False)

    def on_tree_select(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            self.selected_stock_info = None
            return
        
        item = self.tree.item(selected_item[0])
        values = item.get("values")

        # 假设你的 tree 列是 (code, name, price, …)
        stock_info = {
            "code": values[0],
            "name": values[1] if len(values) > 1 else "",
            "extra": values  # 保留整行
        }
        self.selected_stock_info = stock_info
        # 假设 tree 列是 (code, name, price, change, volume)
        # stock_info = {
        #     "code": values[0],
        #     "name": values[1] if len(values) > 1 else "",
        #     "price": values[2] if len(values) > 2 else 0.0,
        #     "change": values[3] if len(values) > 3 else 0.0,
        #     "volume": values[4] if len(values) > 4 else 0,
        #     "extra": values  # 保留整行
        # }
        # self.selected_stock_info = stock_info

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

    # def load_data(self, df):
    #     """加载新的数据到 TreeView"""
    #     self.df_all = df.copy()
    #     self.current_df = df.copy()
    #     self.refresh_tree()

    # def refresh_tree(self):
    #     """刷新 TreeView 显示"""
    #     if self.df_display.empty:
    #         self.tree.delete(*self.tree.get_children())
    #         return

    #     self.tree.delete(*self.tree.get_children())
    #     for idx, row in self.df_display.iterrows():
    #         vals = [row[col] for col in self.df_display.columns]
    #         self.tree.insert("", "end", values=vals)

    # def filter_and_refresh_tree(self, query_dict):
    #     """
    #     query_dict = {
    #         '关键列1': '值或%like%',
    #         '关键列2': '值或%like%',
    #     }
    #     """
    #     if self.df_all.empty:
    #         return
    #     df_filtered = self.df_all.copy()
    #     for col, val in query_dict.items():
    #         if col not in df_filtered.columns:
    #             continue

    #         # 支持模糊 like 查询
    #         if isinstance(val, str) and "%" in val:
    #             pattern = val.replace("%", ".*")
    #             df_filtered = df_filtered[df_filtered[col].astype(str).str.match(pattern)]
    #         else:
    #             df_filtered = df_filtered[df_filtered[col] == val]
    #     # 根据过滤结果保留原始未查询列
    #     self.current_df = self.df_all.loc[df_filtered.index].copy()
    #     self.refresh_tree()


    def update_query_combo(self):
        pass
        # values = [f"{i+1}: {q.get('desc','')} " for i,q in enumerate(self.query_history)]
        # self.query_combo['values'] = values


    def save_query_history(self, query_dict, desc=None):
        if query_dict not in self.query_history:
            self.query_history.append({'query': query_dict, 'desc': desc})

    # def on_query_select(self, event=None):
    #     sel = self.query_combo.current()
    #     if sel < 0:
    #         return
    #     query_dict = self.query_history[sel]['query']
        
    #     # 刷新 TreeView 数据
    #     self.refresh_tree_with_query(query_dict)
        
    #     # 更新查询说明
    #     self.query_desc_label.config(text=self.query_history[sel].get('desc', ''))

    # # 执行查询
    # def on_query(self):
    #     # query_text = self.query_var.get().strip()
    #     query_text = self.query_combo_var.get().strip()
    #     if not query_text:
    #         return
    #     # 构造 query_dict，例如：{'name':'ABC','percent':">1"}
    #     query_dict = self.parse_query_text(query_text)
    #     print(f'query_dict:{query_dict}')
    #     # 保存到历史
    #     desc = query_text  # 简单说明为输入文本
    #     # self.query_history.append({'query': query_dict, 'desc': desc})
    #     self.query_history.append({'query': query_dict})

    #     # 更新下拉框
    #     # self.query_combo['values'] = [q['desc'] for q in self.query_history]
    #     # self.query_combo.current(len(self.query_history)-1)

    #     # 执行刷新
    #     self.refresh_tree_with_query(query_dict)
    #     # self.query_desc_label.config(text=desc)

    # 选择历史查询
    def on_query_select(self, event=None):

        sel = self.query_combo.current()
        # query_text = self.query_combo_var.get()
        # if query_text:
        #     query_dict = query_text
        #     self.on_query(query_dict)
        # else:
        if sel < 0:
            return
        else:
            query_dict = self.query_history[sel]['query']
            # desc = self.query_history[sel].get('desc', '')
            # 更新查询说明
            # self.query_desc_label.config(text=desc)
            self.refresh_tree_with_query(query_dict)

    # TreeView 刷新函数
    # def refresh_tree_with_query(self, query_dict):
    #     if not hasattr(self, 'temp_df'):
    #         return
    #     df = self.temp_df.copy()

    #     # 根据 query_dict 自动过滤
    #     for col, cond in query_dict.items():
    #         if col in df.columns:
    #             if isinstance(cond, str) and cond.startswith(('>', '<', '>=', '<=', '==')):
    #                 df = df.query(f"{col}{cond}")
    #             else:
    #                 df = df[df[col]==cond]

    #     # 只显示 DISPLAY_COLS 列
    #     display_df = df[DISPLAY_COLS]
    #     # 刷新 TreeView
    #     self.tree.delete(*self.tree.get_children())
    #     for idx, row in display_df.iterrows():
    #         self.tree.insert("", "end", values=[row[col] for col in DISPLAY_COLS])

    # 将查询文本解析为 dict（可根据你需求改）
    def parse_query_text(self, text):
        # 简单示例：name=ABC;percent>1
        # result = {}
        # for part in text.split(';'):
        #     if '=' in part:
        #         k,v = part.split('=',1)
        #         result[k.strip()] = v.strip()
        #     elif '>' in part:
        #         k,v = part.split('>',1)
        #         result[k.strip()] = f">{v.strip()}"
        #     elif '<' in part:
        #         k,v = part.split('<',1)
        #         result[k.strip()] = f"<{v.strip()}"
        query_dict = {}
        for cond in text.split(";"):
            cond = cond.strip()
            if not cond:
                continue
            # name%中信 -> key=name, val=%中信
            if "%":
                for op in [">=", "<=", "~", "%"]:
                    if op in cond:
                        key, val = cond.split(op, 1)
                        query_dict[key.strip()] = op + val.strip() if op in [">=", "<="] else val.strip()
                        break
        return query_dict
    #old query_var
    # def on_query(self):
    #     query_text = self.query_var.get()
    #     if not query_text.strip():
    #         self.refresh_tree_with_query(None)
    #         return
    #     query_dict = {}
    #     for cond in query_text.split(";"):
    #         cond = cond.strip()
    #         if not cond:
    #             continue
    #         # name%中信 -> key=name, val=%中信
    #         if "%":
    #             for op in [">=", "<=", "~", "%"]:
    #                 if op in cond:
    #                     key, val = cond.split(op, 1)
    #                     query_dict[key.strip()] = op + val.strip() if op in [">=", "<="] else val.strip()
    #                     break
        
    #     self.save_query_history()
    #     self.refresh_tree_with_query(query_dict)

    def on_query(self):
        query_text = self.query_var.get().strip()
        if not query_text:
            return

        # 构造 query_dict
        query_dict = self.parse_query_text(query_text)

        # 保存到历史
        desc = query_text
        self.query_history.append({'query': query_dict, 'desc': desc})

        # 更新下拉框
        self.query_combo['values'] = [q['desc'] for q in self.query_history]
        if self.query_history:
            self.query_combo.current(len(self.query_history) - 1)

        # 执行刷新
        self.refresh_tree_with_query(query_dict)
        self.query_desc_label.config(text=desc)


    def refresh_tree_with_query(self, query_dict):
        if not hasattr(self, 'temp_df'):
            return
        df = self.temp_df.copy()

        # 支持范围查询和等值查询
        for col, cond in query_dict.items():
            if col not in df.columns:
                continue
            if isinstance(cond, str):
                cond = cond.strip()
                if '~' in cond:  # 区间查询 5~15
                    try:
                        low, high = map(float, cond.split('~'))
                        df = df[(df[col] >= low) & (df[col] <= high)]
                    except:
                        pass
                elif cond.startswith(('>', '<', '>=', '<=', '==')):
                    df = df.query(f"{col}{cond}")
                else:  # 模糊匹配 like
                    df = df[df[col].astype(str).str.contains(cond)]
            else:
                df = df[df[col]==cond]

        # 保留 DISPLAY_COLS
        display_df = df[DISPLAY_COLS]
        self.tree.delete(*self.tree.get_children())
        for idx, row in display_df.iterrows():
            self.tree.insert("", "end", values=[row[col] for col in DISPLAY_COLS])

    def refresh_tree_with_query2(self, query_dict=None):
        """
        刷新 TreeView 并支持高级查询
        query_dict: dict, key=列名, value=查询条件
        """
        if self.df_all.empty:
            return

        # 1. 原始数据保留
        df_raw = self.df_all.copy()

        # 2. 处理查询
        if query_dict:
            df_filtered = df_raw.copy()
            for col, val in query_dict.items():
                if col not in df_filtered.columns:
                    continue
                s = df_filtered[col]
                if isinstance(val, str):
                    val = val.strip()
                    if val.startswith(">="):
                        try:
                            df_filtered = df_filtered[s.astype(float) >= float(val[2:])]
                            continue
                        except: pass
                    elif val.startswith("<="):
                        try:
                            df_filtered = df_filtered[s.astype(float) <= float(val[2:])]
                            continue
                        except: pass
                    elif "~" in val:
                        try:
                            low, high = map(float, val.split("~"))
                            df_filtered = df_filtered[s.astype(float).between(low, high)]
                            continue
                        except: pass
                    elif "%" in val:
                        pattern = val.replace("%", ".*")
                        df_filtered = df_filtered[s.astype(str).str.contains(pattern, regex=True)]
                        continue
                    else:
                        df_filtered = df_filtered[s == val]
                else:
                    df_filtered = df_filtered[s == val]
        else:
            df_filtered = df_raw.copy()

        # 3. 构造显示 DataFrame
        # 仅保留 DISPLAY_COLS，如果 DISPLAY_COLS 中列不在 df_all 中，填充空值
        df_display = pd.DataFrame(index=df_filtered.index)
        for col in DISPLAY_COLS:
            if col in df_filtered.columns:
                df_display[col] = df_filtered[col]
            else:
                df_display[col] = ""

        self.current_df = df_display
        self.refresh_tree()


    def filter_and_refresh_tree(self, query_dict):
        """
        高级过滤 TreeView 显示

        query_dict = {
            'name': '%中%',        # 模糊匹配
            '涨幅': '>=2',         # 数值匹配
            '量': '10~100'         # 范围匹配
        }
        """
        if self.df_all.empty:
            return

        df_filtered = self.df_all.copy()

        for col, val in query_dict.items():
            if col not in df_filtered.columns:
                continue

            s = df_filtered[col]

            # 数值范围或比较符号
            if isinstance(val, str):
                val = val.strip()
                if val.startswith(">="):
                    try:
                        threshold = float(val[2:])
                        df_filtered = df_filtered[s.astype(float) >= threshold]
                        continue
                    except:
                        pass
                elif val.startswith("<="):
                    try:
                        threshold = float(val[2:])
                        df_filtered = df_filtered[s.astype(float) <= threshold]
                        continue
                    except:
                        pass
                elif "~" in val:
                    try:
                        low, high = map(float, val.split("~"))
                        df_filtered = df_filtered[s.astype(float).between(low, high)]
                        continue
                    except:
                        pass
                elif "%" in val:
                    pattern = val.replace("%", ".*")
                    df_filtered = df_filtered[s.astype(str).str.contains(pattern, regex=True)]
                    continue
                else:
                    # 精确匹配
                    df_filtered = df_filtered[s == val]
            else:
                # 数值精确匹配
                df_filtered = df_filtered[s == val]

        # 保留原始未查询列数据，总列数不变
        self.current_df = self.df_all.loc[df_filtered.index].copy()
        self.refresh_tree()

    def refresh_tree(self, df=None):
        # if self.current_df.empty:
        #     self.tree.delete(*self.tree.get_children())
        #     return
        # self.tree.delete(*self.tree.get_children())
        # for idx, row in self.current_df.iterrows():
        #     vals = [row[col] for col in self.df_display.columns]
        #     self.tree.insert("", "end", values=vals)

        if df is None:
            df = self.current_df.copy()

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
        self.alert_manager.save_all()
        self.save_window_position()
        self.save_search_history()
        self.destroy()

# ------------------ 主程序入口 ------------------ #
if __name__ == "__main__":
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
