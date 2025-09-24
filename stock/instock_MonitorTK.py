# -*- coding:utf-8 -*-
import os
import gc
import sys
import time
import json
import threading
import multiprocessing as mp
import tkinter as tk
from tkinter import ttk, filedialog, messagebox,Menu
import pandas as pd
import re
from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import LoggerFactory, commonTips as cct
from JSONData import stockFilter as stf
from JSONData import tdx_data_Day as tdd
import win32pipe, win32file
from datetime import datetime, timedelta
import shutil
log = LoggerFactory.log
# log.setLevel(log_level)
# log.setLevel(LoggerFactory.DEBUG)
# log.setLevel(LoggerFactory.INFO)
# -------------------- 常量 -------------------- #
sort_cols, sort_keys = ct.get_market_sort_value_key('3 0')
DISPLAY_COLS = ct.get_Duration_format_Values(
    ct.Monitor_format_trade,sort_cols[:2])

# DISPLAY_COLS = ct.get_Duration_format_Values(
# ct.Monitor_format_trade,
#     ['name','trade','boll','dff','df2','couts','percent','volume','category']
# )

# ct_MonitorMarket_Values=ct.get_Duration_format_Values(
#                     ct.Monitor_format_trade, market_sort_value[:2])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DARACSV_DIR = os.path.join(BASE_DIR, "datacsv")
WINDOW_CONFIG_FILE = os.path.join(BASE_DIR, "window_config.json")
SEARCH_HISTORY_FILE = os.path.join(DARACSV_DIR, "search_history.json")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archives")
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(DARACSV_DIR, exist_ok=True)
START_INIT = 0
# st_key_sort = '3 0'



# ------------------ 后台数据进程 ------------------ #
def fetch_and_process(shared_dict,queue, blkname="boll", flag=None):
    global START_INIT
    g_values = cct.GlobalValues(shared_dict)  # 主进程唯一实例
    resample = g_values.getkey("resample") or "d"
    market = g_values.getkey("market", "all")        # all / sh / cyb / kcb / bj
    blkname = g_values.getkey("blkname", "061.blk")  # 对应的 blk 文件
    print(f"当前选择市场: {market}, blkname={blkname}")
    st_key_sort =  g_values.getkey("st_key_sort", "3 0") 
    market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(st_key_sort)
    lastpTDX_DF, top_all = pd.DataFrame(), pd.DataFrame()
    print(f"init resample: {resample} flag.value : {flag.value}")
    while True:
        # print(f'resample : new : {g_values.getkey("resample")} last : {resample} st : {g_values.getkey("st_key_sort")}')
        if flag is not None and not flag.value:   # 停止刷新
               time.sleep(1)
               # print(f'flag.value : {flag.value} 停止更新')
               continue
        elif g_values.getkey("resample") and  g_values.getkey("resample") !=  resample:
            # print(f'resample : new : {g_values.getkey("resample")} last : {resample} ')
            top_all = pd.DataFrame()
            lastpTDX_DF = pd.DataFrame()
        elif g_values.getkey("market") and  g_values.getkey("market") !=  market:
            # print(f'market : new : {g_values.getkey("market")} last : {market} ')
            top_all = pd.DataFrame()
            lastpTDX_DF = pd.DataFrame()
        elif g_values.getkey("st_key_sort") and  g_values.getkey("st_key_sort") !=  st_key_sort:
            # print(f'st_key_sort : new : {g_values.getkey("st_key_sort")} last : {st_key_sort} ')
            st_key_sort = g_values.getkey("st_key_sort")
        elif (not cct.get_work_time()) and START_INIT > 0:
                # print(f'not worktime and work_duration')
                time.sleep(5)
                continue
        else:
            print(f'start worktime : {cct.get_now_time()} get_work_time: {cct.get_work_time()} , START_INIT :{START_INIT} ')
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

            if top_all is not None and not top_all.empty:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort,top_all)
            else:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort)

            print(f'sort_cols : {sort_cols} sort_keys : {sort_keys}  st_key_sort : {st_key_sort}')
            top_temp = top_all.copy()
            # if blkname == "boll":
            #     if "market_value" in top_temp.columns:
            #         top_temp = top_temp.dropna(subset=["market_value"])
            #         top_temp["market_value"] = top_temp["market_value"].fillna("0")
            #         top_temp = top_temp[top_temp["market_value"].apply(lambda x: str(x).replace('.','',1).isdigit())]
            #     top_temp = stf.getBollFilter(df=top_temp, resample=resample, down=True)
            #     if top_temp is None:
            #         top_temp = pd.DataFrame(columns=DISPLAY_COLS)

            top_temp=stf.getBollFilter(df=top_temp, resample=resample, down=False)
            top_temp = top_temp.sort_values(by=sort_cols, ascending=sort_keys)
            # print(f'DISPLAY_COLS:{DISPLAY_COLS}')
            # print(f'col: {top_temp.columns.values}')
            # top_temp = top_temp.loc[:, DISPLAY_COLS]
            print(f'top_temp :  {top_temp.loc[:,sort_cols][sort_cols[0]][:5]} shape : {top_temp.shape}')
            queue.put(top_temp)
            gc.collect()
            time.sleep(ct.duration_sleep_time)
            START_INIT = 1
            print(f'START_INIT : {cct.get_now_time()} {START_INIT} fetch_and_process sleep:{ct.duration_sleep_time} resample:{resample}')
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


PIPE_NAME = r"\\.\pipe\my_named_pipe"

def send_code_via_pipe(code):

    if isinstance(code, dict):
        code = json.dumps(code, ensure_ascii=False)

    for _ in range(1):
        try:
            handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None
            )
            # print(f'handle : {handle}')
            win32file.WriteFile(handle, code.encode("utf-8"))
            win32file.CloseHandle(handle)
            return True
        except Exception as e:
            print("发送失败，重试中...", e)
            time.sleep(0.5)
    return False

def list_archives():
    """列出所有存档文件"""
    files = sorted(
        [f for f in os.listdir(ARCHIVE_DIR) if f.startswith("search_history") and f.endswith(".json")],
        reverse=True
    )
    return files


def archive_search_history_list(MONITOR_LIST_FILE=SEARCH_HISTORY_FILE,ARCHIVE_DIR=ARCHIVE_DIR):
    """归档监控文件，避免空或重复存档"""

    if not os.path.exists(MONITOR_LIST_FILE):
        print("⚠ search_history.json 不存在，跳过归档")
        return

    try:
        with open(MONITOR_LIST_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        print(f"⚠ 无法读取监控文件: {e}")
        return

    if not content or content in ("[]", "{}"):
        print("⚠ search_history.json 内容为空，跳过归档")
        return

    # 确保存档目录存在
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # 检查是否和最近一个存档内容相同
    files = sorted(list_archives(), reverse=True)
    if files:
        last_file = os.path.join(ARCHIVE_DIR, files[0])
        try:
            with open(last_file, "r", encoding="utf-8") as f:
                last_content = f.read().strip()
            if not content or content in ("[]", "{}") or content == last_content:
                print("⚠ 内容与上一次存档相同，跳过归档")
                return
        except Exception as e:
            print(f"⚠ 无法读取最近存档: {e}")

    # 生成带日期的存档文件名
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"search_history_{today}.json"
    dest = os.path.join(ARCHIVE_DIR, filename)

    # 如果当天已有存档，加时间戳避免覆盖
    if os.path.exists(dest):
        filename = f"search_history_{today}.json"
        dest = os.path.join(ARCHIVE_DIR, filename)

    # 复制文件
    shutil.copy2(MONITOR_LIST_FILE, dest)
    print(f"✅ 已归档监控文件: {dest}")
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
        self.sortby_col = None
        self.sortby_col_ascend = None
        self.select_code = None
        # 刷新开关标志
        self.refresh_enabled = True
        from multiprocessing import Manager
        self.manager = Manager()
        self.global_dict = self.manager.dict()  # 共享字典
        self.global_dict["resample"] = "d"
        self.global_values = cct.GlobalValues(self.global_dict)
        resample = self.global_values.getkey("resample")
        print(f'app init getkey resample:{self.global_values.getkey("resample")}')
        self.global_values.setkey("resample", resample)
        self.blkname = self.global_values.getkey("blkname") or "061.blk"

        # ----------------- 控件框 ----------------- #
        ctrl_frame = tk.Frame(self)
        ctrl_frame.pack(fill="x", padx=5, pady=2)

        self.st_key_sort = self.global_values.getkey("st_key_sort") or "3 0"
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
        # self.status_var = tk.StringVar()
        # self.status_bar = tk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        # self.status_bar.pack(fill="x", side="bottom")


        # ====== 底部状态栏 ======
        status_frame = tk.Frame(self, relief="sunken", bd=1)
        status_frame.pack(side="bottom", fill="x")

        # 使用 PanedWindow 水平分割，支持拖动
        pw = tk.PanedWindow(status_frame, orient=tk.HORIZONTAL, sashrelief="sunken", sashwidth=4)
        pw.pack(fill="x", expand=True)

        # 左侧状态信息
        left_frame = tk.Frame(pw, bg="#f0f0f0")
        self.status_var = tk.StringVar()
        status_label_left = tk.Label(
            left_frame, textvariable=self.status_var, anchor="w", padx=10, pady=2
        )
        status_label_left.pack(fill="x", expand=True)

        # 右侧状态信息
        right_frame = tk.Frame(pw, bg="#f0f0f0")
        self.status_var2 = tk.StringVar()
        status_label_right = tk.Label(
            right_frame, textvariable=self.status_var2, anchor="e", padx=10, pady=2
        )
        status_label_right.pack(fill="x", expand=True)

        # 添加左右面板
        # pw.add(left_frame, minsize=100)   # 左侧最小宽度
        # pw.add(right_frame, minsize=100)  # 右侧最小宽度
        pw.add(left_frame, minsize=100, width=780)
        pw.add(right_frame, minsize=100, width=220)


        # 设置初始 6:4 比例
        # self.update_idletasks()           # 先刷新窗口获取宽度
        # total_width = pw.winfo_width()
        # pw.sash_place(0, int(total_width * 0.6), 0)

        # 初始化内容
        # self.status_var_left.set("Ready")
        # self.status_var_right.set("Rows: 0")

        # # 底部容器
        # bottom_frame = tk.Frame(self, bg="#f0f0f0")
        # bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # # 左边状态栏
        # left_frame = tk.Frame(bottom_frame, bg="#f0f0f0")
        # left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # self.status_var = tk.StringVar()
        # self.status_label1 = tk.Label(left_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, bg="#f0f0f0", padx=10, pady=2)
        # self.status_label1.pack(fill=tk.X)

        # # 右边任务状态
        # right_frame = tk.Frame(bottom_frame, bg="#f0f0f0")
        # right_frame.pack(side=tk.RIGHT)

        # self.status_var2 = tk.StringVar()
        # self.status_label2 = tk.Label(right_frame, textvariable=self.status_var2, relief=tk.SUNKEN, anchor=tk.W, bg="#f0f0f0", padx=10, pady=2)
        # self.status_label2.pack(fill=tk.X, expand=True)




        # ----------------- TreeView ----------------- #
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        global DISPLAY_COLS
        self.tree = ttk.Treeview(tree_frame, columns=["code"] + DISPLAY_COLS, show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        self.current_cols = ["code"] + DISPLAY_COLS
        # TreeView 列头
        for col in ["code"] + DISPLAY_COLS:
            width = 120 if col=="name" else 80
            self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
            self.tree.column(col, width=width, anchor="center", minwidth=50)
            # self.tree.heading(col, command=lambda c=col: self.show_column_menu(c))

        # 双击表头绑定
        self.tree.bind("<Double-1>", self.on_tree_header_double_click)

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




        # # ========== 右键菜单 ==========
        # self.tree_menu = tk.Menu(self, tearoff=0)
        # self.tree_menu.add_command(label="打开报警中心", command=lambda: open_alert_center(self))
        # self.tree_menu.add_command(label="新建报警规则", command=self.open_alert_rule_new)
        # self.tree_menu.add_command(label="编辑报警规则", command=self.open_alert_rule_edit)

        # 绑定右键点击事件
        self.tree.bind("<Button-3>", self.on_tree_right_click)


        #     self.apply_search()

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
                {"field": "价格", "op": ">=", "value": price, "enabled": True, "delta": 0.1},
                {"field": "涨幅", "op": ">=", "value": change, "enabled": True, "delta": 0.2},
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
            parent.alert_manager.save_rule(stock_code['name'],rule)  # 保存到 AlertManager
            messagebox.showinfo("成功", "规则已保存")
            win.destroy()

        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", pady=10)
        tk.Button(btn_frame, text="保存", command=save_rule).pack(side="left", padx=5)
        tk.Button(btn_frame, text="取消", command=win.destroy).pack(side="left", padx=5)

    def _build_ui(self, ctrl_frame):

        # Market 下拉菜单
        tk.Label(ctrl_frame, text="Market:").pack(side="left", padx=2)

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

        tk.Label(ctrl_frame, text="stkey:").pack(side="left", padx=2)
        self.st_key_sort_value = tk.StringVar()
        self.st_key_sort_entry = tk.Entry(ctrl_frame, textvariable=self.st_key_sort_value,width=5)
        self.st_key_sort_entry.pack(side="left")
        # 绑定回车键提交
        self.st_key_sort_entry.bind("<Return>", self.on_st_key_sort_enter)
        self.st_key_sort_value.set(self.st_key_sort) 
        
        # --- resample 下拉框 ---
        tk.Label(ctrl_frame, text="resample:").pack(side="left")
        self.resample_combo = ttk.Combobox(ctrl_frame, values=["d",'3d', "w", "m"], width=3)
        self.resample_combo.current(0)
        self.resample_combo.pack(side="left", padx=5)
        self.resample_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())
        # --- 刷新按钮 ---
        # tk.Button(ctrl_frame, text="刷新", command=self.refresh_data).pack(side="left", padx=5)

        # 在 __init__ 中

        # self.search_var = tk.StringVar()
        # self.search_combo = ttk.Combobox(ctrl_frame, textvariable=self.search_var, values=self.search_history, width=30)
        # self.search_combo.pack(side="left", padx=5)
        # self.search_combo.bind("<Return>", lambda e: self.apply_search())
        # self.search_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_search())  # 选中历史也刷新
        # tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除历史", command=self.delete_search_history).pack(side="left", padx=2)


        # 在初始化时（StockMonitorApp.__init__）创建并注册：
        self.alert_manager = AlertManager(storage_dir=DARACSV_DIR, logger=log)
        set_global_manager(self.alert_manager)

        # --- 控件区 ---
        # ctrl_frame = tk.Frame(self)
        # ctrl_frame.pack(side="top", fill="x", pady=5)

        # --- 底部搜索框 2 ---
        bottom_search_frame = tk.Frame(self)
        bottom_search_frame.pack(side="bottom", fill="x", pady=2)

        # # --- 顶部工具栏 ---
        # ctrl_frame = tk.Frame(self)
        # ctrl_frame.pack(side="top", fill="x", pady=5)

        # # 功能按钮
        # tk.Button(ctrl_frame, text="停止刷新", command=self.stop_refresh).pack(side="left", padx=5)
        # tk.Button(ctrl_frame, text="启动刷新", command=self.start_refresh).pack(side="left", padx=5)

        # top_search_frame = tk.Frame(ctrl_frame)
        # top_search_frame.pack(side="left", fill="x", expand=True, padx=5)
        # 搜索框 1（在顶部）
        self.search_history1, self.search_history2 = self.load_search_history()
        self.search_var1 = tk.StringVar()
        self.search_combo1 = ttk.Combobox(bottom_search_frame, textvariable=self.search_var1, values=self.search_history1, width=30)
        self.search_combo1.pack(side="left", padx=5, fill="x", expand=True)
        self.search_combo1.bind("<Return>", lambda e: self.apply_search())
        self.search_combo1.bind("<<ComboboxSelected>>", lambda e: self.apply_search())

        # 其他功能按钮
        # tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除历史", command=self.delete_search_history).pack(side="left", padx=2)

        tk.Button(bottom_search_frame, text="清空", command=lambda: self.clean_search(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="删除", command=lambda: self.delete_search_history(1)).pack(side="left", padx=2)


        # 功能选择下拉框（固定宽度）
        options = ["保存数据", "读取存档", "报警中心"]
        self.action_var = tk.StringVar()
        self.action_combo = ttk.Combobox(
            bottom_search_frame, textvariable=self.action_var,
            values=options, state="readonly", width=10
        )
        self.action_combo.set("功能选择")
        self.action_combo.pack(side="left", padx=10, pady=2, ipady=1)

        def run_action(action):
            if action == "停止刷新":
                self.stop_refresh()
            elif action == "启动刷新":
                self.start_refresh()
            elif action == "保存数据":
                self.save_data_to_csv()
            elif action == "读取存档":
                self.load_data_from_csv()
            elif action == "报警中心":
                open_alert_center(self)

        def on_select(event=None):
            run_action(self.action_combo.get())
            self.action_combo.set("功能选择")

        self.action_combo.bind("<<ComboboxSelected>>", on_select)

        self.search_var2 = tk.StringVar()
        self.search_combo2 = ttk.Combobox(ctrl_frame, textvariable=self.search_var2, values=self.search_history2, width=30)
        self.search_combo2.pack(side="left", padx=5, fill="x", expand=True)
        self.search_combo2.bind("<Return>", lambda e: self.apply_search())
        self.search_combo2.bind("<<ComboboxSelected>>", lambda e: self.apply_search())

        # 其他功能按钮
        # tk.Button(bottom_search_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(bottom_search_frame, text="删除历史", command=self.delete_search_history).pack(side="left", padx=2)

        tk.Button(ctrl_frame, text="清空", command=lambda: self.clean_search(2)).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="删除", command=lambda: self.delete_search_history(2)).pack(side="left", padx=2)

        # # 搜索区（可拉伸）
        # search_frame = tk.Frame(ctrl_frame)
        # search_frame.pack(side="left", fill="x", expand=True, padx=5)

        # # self.search_history = self.load_search_history()
        # self.search_history1, self.search_history2 = self.load_search_history()

        # # 第一个搜索框 + 独立历史
        # self.search_var1 = tk.StringVar()
        # self.search_combo1 = ttk.Combobox(search_frame, textvariable=self.search_var1, values=self.search_history1)
        # self.search_combo1.pack(side="left", fill="x", expand=True, padx=(0, 5))
        # self.search_combo1.bind("<Return>", lambda e: self.apply_search())
        # self.search_combo1.bind("<<ComboboxSelected>>", lambda e: self.apply_search())

        # tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除", command=self.delete_search_history).pack(side="left", padx=2)

        # # 第二个搜索框 + 独立历史
        # self.search_var2 = tk.StringVar()
        # self.search_combo2 = ttk.Combobox(search_frame, textvariable=self.search_var2, values=self.search_history2)
        # self.search_combo2.pack(side="left", fill="x", expand=True, padx=(5, 0))
        # self.search_combo2.bind("<Return>", lambda e: self.apply_search())
        # self.search_combo2.bind("<<ComboboxSelected>>", lambda e: self.apply_search())



        # self.search_combo1['values'] = self.search_history1
        # self.search_combo2['values'] = self.search_history2

        # # --------------------
        # # 其他按钮区（固定宽度，不拉伸）
        # tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除", command=self.delete_search_history).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="停止刷新", command=self.stop_refresh).pack(side="left", padx=5)
        # tk.Button(ctrl_frame, text="启动刷新", command=self.start_refresh).pack(side="left", padx=5)

        if len(self.search_history1) > 0:
            self.search_var1.set(self.search_history1[0])
        if len(self.search_history2) > 0:
            self.search_var2.set(self.search_history2[0])
        # self.search_btn1.config(
        #     command=lambda: self.apply_search(self.search_var1, self.search_history1, self.search_combo1, "search1")
        # )
        # self.search_btn2.config(
        #     command=lambda: self.apply_search(self.search_var2, self.search_history2, self.search_combo2, "search2")
        # )

        # ctrl_frame = tk.Frame(self)
        # ctrl_frame.pack(side="top", fill="x", pady=5)

        # # 功能选择
        # combo.pack(side="left", padx=10, pady=2, ipady=1)

        # # 第二搜索框
        # self.search_combo2.pack(side="left", padx=5)

        # # 原搜索框
        # self.search_combo.pack(side="left", padx=5)


        #2
        # options = ["保存数据", "读取存档", "停止刷新", "启动刷新", "报警中心"]

        # self.action_var = tk.StringVar()
        # combo = ttk.Combobox(ctrl_frame, textvariable=self.action_var, values=options, state="readonly")
        # combo.set("选择操作")  # 默认提示
        # combo.pack(side="left", padx=5)

        # def on_select(event=None):
        #     run_action(combo.get())

        # combo.bind("<<ComboboxSelected>>", on_select)

        # # --- 数据存档按钮 ---
        # tk.Button(ctrl_frame, text="保存数据", command=self.save_data_to_csv).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="读取存档", command=self.load_data_from_csv).pack(side="left", padx=2)

        # # --- 刷新控制按钮 ---
        # tk.Button(ctrl_frame, text="停止刷新", command=self.stop_refresh).pack(side="left", padx=5)
        # tk.Button(ctrl_frame, text="启动刷新", command=self.start_refresh).pack(side="left", padx=2)

        #         # 在初始化时（StockMonitorApp.__init__）创建并注册：
        # self.alert_manager = AlertManager(storage_dir=DARACSV_DIR, logger=log)
        # set_global_manager(self.alert_manager)
        # # 在 UI 控件区加个按钮：
        # tk.Button(ctrl_frame, text="报警中心", command=lambda: open_alert_center(self)).pack(side="left", padx=2)


    def replace_st_key_sort_col(self, old_col, new_col):
        """替换显示列并刷新表格"""
        if old_col in self.current_cols and new_col not in self.current_cols:
            print(f'old_col : {old_col} new_col {new_col} self.current_cols : {self.current_cols}')
            idx = self.current_cols.index(old_col)
            self.current_cols[idx] = new_col

            # 去掉重复列
            new_columns = []
            for col in ["code"] + self.current_cols:
                if col not in new_columns:
                    new_columns.append(col)

            # 确保 Treeview 先注册所有列
            for col in new_columns:
                if col not in self.tree["columns"]:
                    self.tree["columns"] = list(self.tree["columns"]) + [col]
            # # 重新设置 tree 的列集合
            # if "code" not in self.current_cols:
            #     new_columns = ["code"] + self.current_cols
            # else:
            #     new_columns = self.current_cols

            self.tree.config(columns=new_columns)

            # 重新设置表头
            for col in new_columns:
                # self.tree.heading(col, text=col, anchor="center")
                self.tree.heading(col, text=col, anchor="center", command=lambda _col=col: self.sort_by_column(_col, False))
                                  # command=lambda c=col: self.show_column_menu(c))

            # 重新加载数据
            self.refresh_tree(self.df_all)
            # self.apply_search()


    def on_st_key_sort_enter(self, event):
        sort_val = self.st_key_sort_value.get()
        # try:
        #     nums = list(map(int, sort_val.strip().split()))
        #     if len(nums) != 2:
        #         raise ValueError
        # except:
        #     print("输入格式错误，例如：'3 0'")
        #     return
        def diff_and_replace_all(old_cols, new_cols):
            """找出两个列表不同的元素，返回替换规则 (old, new)"""
            replace_rules = []
            for old, new in zip(old_cols, new_cols):
                if old != new:
                    replace_rules.append((old, new))
            return replace_rules
            #
            # diffs = diff_and_replace(DISPLAY_COLS, DISPLAY_COLS_2)
            # for old_col, new_col in diffs:
            #     self.replace_st_key_sort_col(old_col, new_col)

        def first_diff(old_cols, new_cols):
            for old, new in zip(old_cols, new_cols):
                if old != new:
                    return old, new
            return None

        if sort_val:
            # global DISPLAY_COLS
            sort_val = sort_val.strip()
            self.global_values.setkey("st_key_sort", sort_val)
            self.status_var.set(f"设置 st_key_sort : {sort_val}")
            self.st_key_sort = sort_val
            self.sortby_col = None
            self.sortby_col_ascend = None
            self.select_code = None

            if self.df_all is not None and not self.df_all.empty:
                sort_cols, sort_keys = ct.get_market_sort_value_key(sort_val,self.df_all)
            else:
                sort_cols, sort_keys = ct.get_market_sort_value_key(sort_val)

            DISPLAY_COLS_2 = ct.get_Duration_format_Values(
                ct.Monitor_format_trade,sort_cols[:2])
            # print(f'DISPLAY_COLS : {DISPLAY_COLS}')
            # print(f'DISPLAY_COLS_2 : {DISPLAY_COLS_2}')
            diff = first_diff(self.current_cols[1:], DISPLAY_COLS_2)
            if diff:
                print(f'diff : {diff}')
                self.replace_st_key_sort_col(*diff)
            DISPLAY_COLS = DISPLAY_COLS_2
            self.current_cols = ["code"] + DISPLAY_COLS_2

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

    def format_next_time(self,delay_ms=None):
        """把 root.after 的延迟时间转换成 %H:%M 格式"""
        if delay_ms == None:
            target_time = datetime.now()
        else:
            delay_sec = delay_ms / 1000
            target_time = datetime.now() + timedelta(seconds=delay_sec)
        return target_time.strftime("%H:%M")
    # ----------------- 数据刷新 ----------------- #
    def update_tree(self):
        try:
            if self.refresh_enabled:  # ✅ 只在启用时刷新
                while not self.queue.empty():
                    df = self.queue.get_nowait()
                    # print(f'df:{df[:1]}')
                    if self.sortby_col is not None:
                        print(f'update_tree sortby_col : {self.sortby_col} sortby_col_ascend : {self.sortby_col_ascend}')
                        df = df.sort_values(by=self.sortby_col, ascending=self.sortby_col_ascend)
                    self.df_all = df.copy()
                    if self.search_var1.get() or self.search_var2.get():
                        self.apply_search()
                    else:
                        self.refresh_tree(df)
                    self.status_var2.set(f'queue update: {self.format_next_time()}')
        except Exception as e:
            log.error(f"Error updating tree: {e}", exc_info=True)
        finally:
            self.after(1000, self.update_tree)

    def push_stock_info(self,stock_code, row):
        """
        从 self.df_all 的一行数据提取 stock_info 并推送
        """
        try:
            stock_info = {
                "code": str(stock_code),
                "name": str(row["name"]),
                "high": str(row["high"]),
                "lastp1d": str(row["lastp1d"]),
                "percent": float(row.get("percent", 0)),
                "price": float(row.get("close", 0)),
                "volume": int(row.get("volume", 0))
            }
            # code, _ , percent,price, vol
            # 转为 JSON 字符串
            payload = json.dumps(stock_info, ensure_ascii=False)

            # ---- 根据传输方式选择 ----
            # 如果用 WM_COPYDATA，需要 encode 成 bytes 再传
            # if hasattr(self, "send_wm_copydata"):
            #     self.send_wm_copydata(payload.encode("utf-8"))

            # 如果用 Pipe / Queue，可以直接传 str
            # elif hasattr(self, "pipe"):
            #     self.pipe.send(payload)


            # 推送给异动联动（用管道/消息）
            send_code_via_pipe(payload)   # 假设你用 multiprocessing.Pipe
            # 或者 self.queue.put(stock_info)  # 如果是队列
            # 或者 send_code_to_other_window(stock_info) # 如果是 WM_COPYDATA
            log.info(f"推送: {stock_info}")
            return True
        except Exception as e:
            log.error(f"推送 stock_info 出错: {e} {row}")
            return False

    def on_tree_right_click(self, event):
        """右键点击 TreeView 行"""
        # 确保选中行
        item_id = self.tree.identify_row(event.y)
        # if item_id:
        #     self.tree.selection_set(item_id)
            # self.tree_menu.post(event.x_root, event.y_root)
        # selected_item = self.tree.selection()

        if item_id:
            stock_info = self.tree.item(item_id, 'values')
            stock_code = stock_info[0]
            if self.push_stock_info(stock_code,self.df_all.loc[stock_code]):
                # 如果发送成功，更新状态标签
                self.status_var2.set(f"发送成功: {stock_code}")
            else:
                # 如果发送失败，更新状态标签
                self.status_var2.set(f"发送失败: {stock_code}")


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
            # send_tdx_Key = False
            # if self.select_code: 
            #     if stock_code != self.select_code:
            #         self.select_code =  stock_code
            #         send_tdx_Key = True
            # else:
            #     send_tdx_Key = True
            #     self.select_code =  stock_code
            #gpt 精简逻辑
            # send_tdx_Key = (self.select_code is None or self.select_code != stock_code)
            # self.select_code = stock_code

            send_tdx_Key = (self.select_code != stock_code)
            self.select_code = stock_code

            stock_code = str(stock_code).zfill(6)
            log.info(f'stock_code:{stock_code}')
            # send_to_tdx(stock_code)   # 根据你的逻辑发送到 TDX 或其他
            print(f"选中股票代码: {stock_code}")
            if send_tdx_Key and stock_code:
                self.sender.send(stock_code)


    def update_send_status(self, status_dict):
        # 更新状态栏
        status_text = f"TDX: {status_dict['TDX']} | THS: {status_dict['THS']} | DC: {status_dict['DC']}"
        # self.status_var.set(status_text)
        print(status_text)

    # ----------------- Checkbuttons ----------------- #
    def init_checkbuttons(self, parent_frame):
        frame_right = tk.Frame(parent_frame, bg="#f0f0f0")
        frame_right.pack(side=tk.RIGHT, padx=2, pady=2)

        self.tdx_var = tk.BooleanVar(value=True)
        self.ths_var = tk.BooleanVar(value=True)
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

    # def refresh_tree1(self, df=None):
    #     if df is None:
    #         df = self.current_df.copy()

    #     for i in self.tree.get_children():
    #         self.tree.delete(i)

    #     if df.empty:
    #         self.current_df = df
    #         self.update_status()
    #         return

    #     df = df.copy()
    #     # 确保 code 列存在
    #     if 'code' not in df.columns:
    #         df.insert(0, "code", df.index)
    #     cols_to_show = ['code'] + [c for c in DISPLAY_COLS if c != 'code']
    #     df = df.reindex(columns=cols_to_show)

    #     # 自动搜索过滤 初始版本的query
    #     # query = self.search_var.get().strip()
    #     # if query:
    #     #     try:
    #     #         df = df.query(query)
    #     #     except Exception as e:
    #     #         log.error(f"自动搜索过滤错误: {e}")

    #     # 插入到 TreeView
    #     for _, row in df.iterrows():
    #         self.tree.insert("", "end", values=list(row))

    #     self.current_df = df
    #     self.adjust_column_widths()
    #     self.update_status()


    def open_column_selector(self, col_index):
        """弹出横排窗口选择新的列名"""
        if self.current_df is None or self.current_df.empty:
            return

        # 创建弹出窗口
        win = tk.Toplevel(self)
        win.title("选择列")
        win.geometry("800x400")  # 可调大小
        win.transient(self)

        # 滚动条 + 画布 + frame，避免列太多放不下
        canvas = tk.Canvas(win)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 当前所有列
        all_cols = list(self.current_df.columns)

        def on_select(col_name):
            # 替换 Treeview 的列
            if 0 <= col_index < len(DISPLAY_COLS):
                DISPLAY_COLS[col_index] = col_name
                self.refresh_tree(self.current_df)
            win.destroy()

        # 生成按钮（横排，自动换行）
        for i, col in enumerate(all_cols):
            btn = tk.Button(scroll_frame, text=col, width=15,
                            command=lambda c=col: on_select(c))
            btn.grid(row=i // 5, column=i % 5, padx=5, pady=5, sticky="w")

        win.grab_set()  # 模态

    def on_tree_header_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":  # 确认点击在表头
            col = self.tree.identify_column(event.x)
            col_index = int(col.replace("#", "")) - 1
            if 0 <= col_index < len(self.tree["columns"]):
                col_name = self.tree["columns"][col_index]
                self.show_column_menu(col_name,event)  # 弹出列选择菜单

    # def show_column_menu(self, current_col=None):
    #     """弹出列选择窗口，自动自适应行列布局"""
    #     all_cols = list(self.df_all.columns)  # 全部列来源
    #     selected_cols = getattr(self, "display_cols", list(self.tree["columns"]))

    #     win = tk.Toplevel(self)
    #     win.title("选择显示列")
    #     win.geometry("500x400")
    #     win.transient(self)
    #     win.grab_set()

    #     frm = tk.Frame(win)
    #     frm.pack(fill="both", expand=True, padx=10, pady=10)

    #     n = len(all_cols)
    #     max_cols_per_row = 5  # 每行最多 5 个，可改
    #     cols_per_row = min(n, max_cols_per_row)
    #     nrows = math.ceil(n / cols_per_row)

    #     var_map = {}
    #     for i, col in enumerate(all_cols):
    #         var = tk.BooleanVar(value=(col in selected_cols))
    #         var_map[col] = var
    #         r = i // cols_per_row
    #         c = i % cols_per_row
    #         cb = tk.Checkbutton(frm, text=col, variable=var, anchor="w")
    #         cb.grid(row=r, column=c, sticky="w", padx=4, pady=2)

    #     def apply_cols():
    #         new_cols = [col for col, var in var_map.items() if var.get()]
    #         if not new_cols:
    #             tk.messagebox.showwarning("提示", "至少选择一列")
    #             return
    #         self.display_cols = new_cols
    #         self.tree["columns"] = ["code"] + new_cols
    #         for col in self.tree["columns"]:
    #             self.tree.heading(col, text=col, anchor="center")
    #         win.destroy()
    #         self.refresh_tree()

    #     tk.Button(win, text="应用", command=apply_cols).pack(side="bottom", pady=6)

    # def show_column_menu1(self, col):
    #     """表头点击后弹出列替换菜单"""
    #     menu = Menu(self, tearoff=0)

    #     # 显示 df_all 所有列（除了已经在 current_cols 的）
    #     for new_col in self.df_all.columns:
    #         if new_col not in self.current_cols:
    #             menu.add_command(
    #                 label=f"替换 {col} → {new_col}",
    #                 command=lambda nc=new_col, oc=col: self.replace_column(oc, nc)
    #             )

    #     # 弹出菜单
    #     menu.post(self.winfo_pointerx(), self.winfo_pointery())

    # def show_column_menu(self, col):
    #     # 弹出一个 Toplevel 网格窗口显示 df_all 的列，点击即可替换
    #     win = tk.Toplevel(self)
    #     win.transient(self)  # 弹窗在父窗口之上
    #     win.grab_set()
    #     win.title(f"替换列: {col}")

    #     # 过滤掉已经在 current_cols 的列
    #     all_cols = [c for c in self.df_all.columns if c not in self.current_cols or c == col]

    #     # 网格排列参数
    #     cols_per_row = 5  # 每行显示5个按钮，可根据需要调整
    #     btn_width = 15
    #     btn_height = 1

    #     for i, c in enumerate(all_cols):
    #         btn = tk.Button(win,
    #                         text=c,
    #                         width=btn_width,
    #                         height=btn_height,
    #                         command=lambda nc=c, oc=col: [self.replace_column(oc, nc), win.destroy()])
    #         btn.grid(row=i // cols_per_row, column=i % cols_per_row, padx=2, pady=2)



    # def _show_column_menu(self, col ,event):
    #     # 找到列
    #     # col = self.tree.identify_column(event.x)
    #     # col_idx = int(col.replace('#','')) - 1
    #     # col_name = self.current_cols[col_idx]
    #     def default_filter(c):
    #         if c in self.current_cols:
    #             return False
    #         if any(k in c.lower() for k in ["perc","percent","trade","volume","boll","macd","ma"]):
    #             return True
    #         return False
    #     # 弹窗位置在鼠标指针
    #     x = event.x_root
    #     y = event.y_root

    #     win = tk.Toplevel(self)
    #     win.transient(self)
    #     win.grab_set()
    #     win.title(f"替换列: {col}")
    #     win.geometry(f"+{x}+{y}")

    #     # all_cols = [c for c in self.df_all.columns if c not in self.current_cols or c == col]
    #     all_cols = [c for c in self.df_all.columns if default_filter(c)]
    #     # 自动计算网格布局
    #     n = len(all_cols)
    #     if n <= 10:
    #         cols_per_row = min(n, 5)
    #     else:
    #         cols_per_row = 5

    #     for i, c in enumerate(all_cols):
    #         btn = tk.Button(win, text=c, width=12, command=lambda nc=c, oc=col: [self.replace_column(oc, nc), win.destroy()])
    #         btn.grid(row=i // cols_per_row, column=i % cols_per_row, padx=2, pady=2)

    def show_column_menu(self, col, event):
        """
        右键弹出选择列菜单。
        col: 当前列
        event: 鼠标事件，用于获取指针位置
        """
        if not hasattr(self, "_menu_frame"):
            self._menu_frame = None  # 防止重复弹出

        # 防止多次重复弹出
        if self._menu_frame and self._menu_frame.winfo_exists():
            self._menu_frame.destroy()

        # 获取当前鼠标指针位置
        x = event.x_root
        y = event.y_root

        # 创建顶级 Frame，用于承载按钮
        menu_frame = tk.Toplevel(self)
        menu_frame.overrideredirect(True)  # 去掉标题栏
        menu_frame.geometry(f"+{x}+{y}")
        self._menu_frame = menu_frame

        # 添加一个搜索框
        search_var = tk.StringVar()
        search_entry = ttk.Entry(menu_frame, textvariable=search_var)
        search_entry.pack(fill="x", padx=4, pady=2)

        # 布局按钮 Frame
        btn_frame = ttk.Frame(menu_frame)
        btn_frame.pack(fill="both", expand=True)


        # 默认防抖刷新
        def refresh_buttons():
            # 清空旧按钮
            for w in btn_frame.winfo_children():
                w.destroy()
            # 获取搜索过滤
            key = search_var.get().lower()
            filtered = [c for c in all_cols if key in c.lower()]
            # 自动计算行列布局
            n = len(filtered)
            if n == 0:
                return
            cols_per_row = min(6, n)  # 每行最多6个
            rows = (n + cols_per_row - 1) // cols_per_row
            for idx, c in enumerate(filtered):
                btn = ttk.Button(btn_frame, text=c,
                                 command=lambda nc=c: self.replace_column(col, nc))
                btn.grid(row=idx // cols_per_row, column=idx % cols_per_row, padx=2, pady=2, sticky="nsew")

            # 自动扩展列宽
            for i in range(cols_per_row):
                btn_frame.columnconfigure(i, weight=1)

        def default_filter(c):
            if c in self.current_cols:
                return False
            # keywords = ["perc","percent","trade","volume","boll","macd","ma"]
            keywords = ["perc","percent","trade","volume","macd","ma"]
            return any(k in c.lower() for k in keywords)

        # 防抖机制
        def on_search_changed(*args):
            if hasattr(self, "_search_after_id"):
                self.after_cancel(self._search_after_id)
            self._search_after_id = self.after(200, refresh_buttons)

        # 获取可选列，排除当前已经显示的
        # all_cols = [c for c in self.df_all.columns if c not in self.current_cols]   
        all_cols = [c for c in self.df_all.columns if default_filter(c)]

        search_var.trace_add("write", on_search_changed)

        # 初次填充
        refresh_buttons()

        # 点击其他地方关闭菜单
        def close_menu(event=None):
            if menu_frame.winfo_exists():
                menu_frame.destroy()

        menu_frame.bind("<FocusOut>", close_menu)
        menu_frame.focus_force()


    # def show_column_menu_(self, col ,event):

    #     x = event.x_root
    #     y = event.y_root


    #     # 创建顶级 Frame，用于承载按钮
    #     # menu_frame = tk.Toplevel(self)
    #     # menu_frame.overrideredirect(True)  # 去掉标题栏
    #     # menu_frame.geometry(f"+{x}+{y}")
    #     # self._menu_frame = menu_frame

    #     # # 添加一个搜索框
    #     # search_var = tk.StringVar()
    #     # search_entry = ttk.Entry(menu_frame, textvariable=search_var)
    #     # search_entry.pack(fill="x", padx=4, pady=2)

    #     # # 布局按钮 Frame
    #     # btn_frame = ttk.Frame(menu_frame)
    #     # btn_frame.pack(fill="both", expand=True)


    #     win = tk.Toplevel(self)
    #     # win.overrideredirect(True) 
    #     win.transient(self)
    #     win.grab_set()
    #     win.title(f"替换列: {col}")
    #     win.geometry(f"+{x}+{y}")

    #     # 搜索框
    #     tk.Label(win, text="搜索列:").grid(row=0, column=0, sticky="w")
    #     search_var = tk.StringVar()
    #     search_entry = tk.Entry(win, textvariable=search_var, width=20)
    #     search_entry.grid(row=0, column=1, columnspan=4, sticky="we", padx=2, pady=2)
    #     # search_var.trace_add("write", lambda *args: refresh_buttons())

    #     # 按钮显示框架
    #     btn_frame = tk.Frame(win)
    #     btn_frame.grid(row=1, column=0, columnspan=5, padx=2, pady=2)

    #     # 默认筛选规则
    #     def default_filter(c):
    #         if c in self.current_cols:
    #             return False
    #         keywords = ["perc","percent","trade","volume","boll","macd","ma"]
    #         return any(k in c.lower() for k in keywords)

    #     def on_search_changed(event):
    #         if hasattr(self, "_search_after_id"):
    #             self.after_cancel(self._search_after_id)
    #         self._search_after_id = self.after(300, refresh_buttons)
    #     all_cols = [c for c in self.df_all.columns if default_filter(c)]

    #     search_entry.bind("<KeyRelease>", on_search_changed)

    #     # 刷新按钮
    #     # def refresh_buttons():
    #     #     # 清空旧按钮
    #     #     for w in btn_frame.winfo_children():
    #     #         w.destroy()
    #     #     kw = search_var.get().lower()
    #     #     filtered = [c for c in all_cols if kw in c.lower()]
    #     #     n = len(filtered)
    #     #     cols_per_row = 5 if n > 5 else n
    #     #     for i, c in enumerate(filtered):
    #     #         btn = tk.Button(btn_frame, text=c, width=12,
    #     #                         command=lambda nc=c, oc=col: [self.replace_column(oc, nc), win.destroy()])
    #     #         btn.grid(row=i // cols_per_row, column=i % cols_per_row, padx=2, pady=2)
    #     def refresh_buttons():
    #         for w in btn_frame.winfo_children():
    #             w.destroy()
    #         kw = search_var.get().lower()

    #         # 搜索匹配所有列，但排除已经在 current_cols 的
    #         if kw:
    #             filtered = [c for c in self.df_all.columns if kw in c.lower() and c not in self.current_cols]
    #         else:
    #             # 默认显示符合默认规则且不在 current_cols
    #             keywords = ["perc","percent","trade","volume","boll","macd","ma"]
    #             filtered = [c for c in self.df_all.columns if any(k in c.lower() for k in keywords) and c not in self.current_cols]

    #         n = len(filtered)
    #         cols_per_row = 5 if n > 5 else n
    #         for i, c in enumerate(filtered):
    #             btn = tk.Button(btn_frame, text=c, width=12,
    #                             command=lambda nc=c, oc=col: [self.replace_column(oc, nc), win.destroy()])
    #             btn.grid(row=i // cols_per_row, column=i % cols_per_row, padx=2, pady=2)
    #     # 防抖机制
    #     def on_search_changed(*args):
    #         if hasattr(self, "_search_after_id"):
    #             self.after_cancel(self._search_after_id)
    #         self._search_after_id = self.after(200, refresh_buttons)

    #     refresh_buttons()
    #     # 点击其他地方关闭菜单
    #     # def close_menu(event=None):
    #     #     if win.winfo_exists():
    #     #         win.destroy()

    #     # win.bind("<FocusOut>", close_menu)
    #     # win.focus_force()

    def replace_column(self, old_col, new_col):
        """替换显示列并刷新表格"""

        if old_col in self.current_cols:
            idx = self.current_cols.index(old_col)
            self.current_cols[idx] = new_col

            # 重新设置 tree 的列集合
            if "code" not in self.current_cols:
                new_columns = ["code"] + self.current_cols
            else:
                new_columns = self.current_cols

            self.tree.config(columns=new_columns)

            # 重新设置表头
            for col in new_columns:
                # self.tree.heading(col, text=col, anchor="center")
                self.tree.heading(col, text=col, anchor="center", command=lambda _col=col: self.sort_by_column(_col, False))
                                  # command=lambda c=col: self.show_column_menu(c))

            # 重新加载数据
            # self.refresh_tree(self.df_all)
            self.apply_search()


    def refresh_tree(self, df=None):
        """刷新 TreeView，保证列和数据严格对齐。"""
        if df is None:
            df = self.current_df.copy()

        # 清空
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        # 若 df 为空，更新状态并返回
        if df is None or df.empty:
            # self.current_df = df
            self.current_df = pd.DataFrame() if df is None else df
            self.update_status()
            return

        df = df.copy()

        # 确保 code 列存在并为字符串（便于显示）
        if 'code' not in df.columns:
            # 将 index 转成字符串放到 code 列
            df.insert(0, 'code', df.index.astype(str))

        # 要显示的列顺序（把 DISPLAY_COLS 的顺序保持一致）
        # cols_to_show = ['code'] + [c for c in DISPLAY_COLS if c != 'code']
        cols_to_show = [c for c in self.current_cols if c in df.columns]
        # print(f'cols_to_show : {cols_to_show}')
        # self.tree.config(columns=cols_to_show)
        # self.tree["displaycolumns"] = cols_to_show


        # 插入数据严格按 cols_to_show
        for _, row in df.iterrows():
            values = [row.get(col, "") for col in cols_to_show]
            self.tree.insert("", "end", values=values)

        # cols_to_show =  self.current_cols
        # # 插入数据严格按 cols_to_show
        # for _, row in df.iterrows():
        #     values = [row.get(col, "") for col in cols_to_show]
        #     self.tree.insert("", "end", values=values)




        # 如果 Treeview 的 columns 与我们想要的不一致，则重新配置
        current_cols = list(self.tree["columns"])
        if current_cols != cols_to_show:
            # 关键：更新 columns，确保使用 list/tuple（不要使用 numpy array）
            self.tree.config(columns=cols_to_show)
            # 强制只显示 headings（隐藏 #0），并设置 displaycolumns 显示顺序
            self.tree.configure(show='headings')
            self.tree["displaycolumns"] = cols_to_show

            # 清理旧的 heading/column 配置，然后为每列重新设置 heading 和 column
            for col in cols_to_show:
                # 用默认参数避免 lambda 闭包问题
                self.tree.heading(col, text=col, command=lambda _c=col: self.sort_by_column(_c, False))
                # 初始宽度，可以根据需要调整
                width = 120 if col == "name" else 80
                self.tree.column(col, width=width, anchor="center", minwidth=50)

        # 插入数据：**严格按 cols_to_show 的顺序选取值**（防止错位）
        # for _, row in df.iterrows():
        #     values = []
        #     for col in cols_to_show:
        #         if col in df.columns:
        #             # 避免 NaN 导致显示 "nan"
        #             v = row[col]
        #             values.append("" if pd.isna(v) else v)
        #         else:
        #             values.append("")
        #     self.tree.insert("", "end", values=values)


        # 4. 恢复选中
        if self.select_code:
            print(f'self.select_code: {self.select_code}')
            for iid in self.tree.get_children():
                values = self.tree.item(iid, "values")
                if values and values[0] == self.select_code:
                    self.tree.selection_add(iid)
                    self.tree.see(iid)  # 自动滚动到可见位置
                    break
        # 双击表头绑定
        self.tree.bind("<Double-1>", self.on_tree_header_double_click)
        # 保存完整数据（方便后续 query / 显示切换）
        self.current_df = df
        # 调整列宽
        self.adjust_column_widths()
        # 更新状态栏
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

    # def adjust_column_widths(self):
    #     # 只调整 Treeview 中存在的列
    #     for col in self.tree["columns"]:
    #         if col in self.current_df.columns:
    #             max_len = max([len(str(val)) for val in self.current_df[col]] + [len(col)])
    #             width = min(max(max_len * 10, 60), 300)
    #             if col == 'name':
    #                 width = int(width * 1.8)
    #             self.tree.column(col, width=width)

    def adjust_column_widths(self):
        """根据当前 self.current_df 和 tree 的列调整列宽（只作用在 display 的列）"""
        # cols = list(self.tree["displaycolumns"]) if self.tree["displaycolumns"] else list(self.tree["columns"])
        cols = list(self.tree["columns"])
        # 遍历显示列并设置合适宽度
        for col in cols:
            # 跳过不存在于 df 的列
            if col not in self.current_df.columns:
                # 仍要确保列有最小宽度
                self.tree.column(col, width=80)
                continue
            # 计算列中最大字符串长度
            try:
                max_len = max([len(str(x)) for x in self.current_df[col].fillna("").values] + [len(col)])
            except Exception:
                max_len = len(col)
            width = min(max(max_len * 8, 60), 300)  # 经验值：每字符约8像素，可调整
            if col == 'name':
                width = int(width * 1.6)
            self.tree.column(col, width=width)

    # ----------------- 排序 ----------------- #
    def sort_by_column(self, col, reverse):
        if col in ['code'] or col not in self.current_df.columns:
            return
        self.select_code = None
        self.sortby_col =  col
        self.sortby_col_ascend = not reverse
        df_sorted = self.current_df.sort_values(by=col, ascending=not reverse)
        self.refresh_tree(df_sorted)
        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))

    # def save_search_history(self):
    #     try:
    #         with open(SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
    #             json.dump(self.search_history, f, ensure_ascii=False, indent=2)
    #     except Exception as e:
    #         log.error(f"保存搜索历史失败: {e}")

    # def load_search_history(self):
    #     if os.path.exists(SEARCH_HISTORY_FILE):
    #         try:
    #             with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
    #                 return json.load(f)
    #         except Exception as e:
    #             log.error(f"加载搜索历史失败: {e}")
    #     return []
    # SEARCH_HISTORY_FILE = "search_history.json"

    def save_search_history(self):
        """保存两个搜索框的历史到一个文件，自动去重"""
        try:
            # 用 dict.fromkeys() 保留顺序去重
            self.search_history1 = list(dict.fromkeys(self.search_history1))
            self.search_history2 = list(dict.fromkeys(self.search_history2))

            data = {
                "history1": self.search_history1,
                "history2": self.search_history2
            }
            with open(SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"保存搜索历史失败: {e}")

    def load_search_history(self):
        """从文件加载两个搜索框的历史"""
        if os.path.exists(SEARCH_HISTORY_FILE):
            try:
                with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("history1", []), data.get("history2", [])
            except Exception as e:
                log.error(f"加载搜索历史失败: {e}")
        return [], []

    # def apply_search_single(self, query, history_list, combo):
    #     """执行单个搜索框的搜索逻辑"""
    #     query = query.strip()
    #     if not query:
    #         self.status_var.set("搜索框为空")
    #         return

    #     # --- 插入历史：先去掉旧的，再插到最前面 ---
    #     if query in history_list:
    #         history_list.remove(query)
    #     history_list.insert(0, query)

    #     # 保留最多 20 条
    #     history_list[:] = history_list[:20]

    #     # 更新到 combobox
    #     combo['values'] = history_list
    #     self.save_search_history()  # 存档时也会去重

    #     # --- 数据过滤 ---
    #     if self.df_all.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     try:
    #         df_filtered = self.df_all.query(query)
    #         self.refresh_tree(df_filtered)
    #         self.status_var.set(f"搜索: {query} | 结果 {len(df_filtered)} 行")
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")


    def apply_search(self):
        val1 = self.search_var1.get().strip()
        val2 = self.search_var2.get().strip()

        if not val1 and not val2:
            self.status_var.set("搜索框为空")
            return

        # 构建原始查询语句
        if val1 and val2:
            query = f"({val1}) and ({val2})"
        elif val1:
            query = val1
        else:
            query = val2

        try:
            # 顶部搜索框
            if val1:
                if val1 in self.search_history1:
                    self.search_history1.remove(val1)
                self.search_history1.insert(0, val1)
                if len(self.search_history1) > 20:
                    self.search_history1[:] = self.search_history1[:20]
                self.search_combo1['values'] = self.search_history1
                try:
                    self.search_combo1.set(val1)
                except Exception:
                    pass

            # 底部搜索框
            if val2:
                if val2 in self.search_history2:
                    self.search_history2.remove(val2)
                self.search_history2.insert(0, val2)
                if len(self.search_history2) > 20:
                    self.search_history2[:] = self.search_history2[:20]
                self.search_combo2['values'] = self.search_history2
                try:
                    self.search_combo2.set(val2)
                except Exception:
                    pass

            # 一次性保存
            self.save_search_history()
        except Exception as ex:
            log.exception("更新搜索历史时出错: %s", ex)

        # ================= 数据为空检查 =================
        if self.df_all.empty:
            self.status_var.set("当前数据为空")
            return

        # ====== 条件清理 ======
        import re
        conditions = [c.strip() for c in query.split('and')]
        valid_conditions = []
        removed_conditions = []

        for cond in conditions:
            cond_clean = cond.lstrip('(').rstrip(')')

            # index 条件特殊保留
            # if 'index.' in cond_clean.lower():
            #     valid_conditions.append(cond_clean)
            #     continue

            # index 或 str 操作条件特殊保留
            if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower():
                valid_conditions.append(cond_clean)
                continue


            # 提取条件中的列名
            cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)

            # 所有列都必须存在才保留
            if all(col in self.df_all.columns for col in cols_in_cond):
                valid_conditions.append(cond_clean)
            else:
                removed_conditions.append(cond_clean)
                log.info(f"剔除不存在的列条件: {cond_clean}")

        # 打印剔除条件列表
        if removed_conditions:
            print(f"[剔除的条件列表] {removed_conditions}")

        if not valid_conditions:
            self.status_var.set("没有可用的查询条件")
            return

        # ====== 拼接 final_query 并检查括号 ======
        final_query = ' and '.join(f"({c})" for c in valid_conditions)

        left_count = final_query.count("(")
        right_count = final_query.count(")")
        if left_count != right_count:
            if left_count > right_count:
                final_query += ")" * (left_count - right_count)
            elif right_count > left_count:
                final_query = "(" * (right_count - left_count) + final_query

        # ====== 决定 engine ======
        query_engine = 'numexpr'
        if any('index.' in c.lower() for c in valid_conditions):
            query_engine = 'python'

        # ====== 数据过滤 ======
        try:
            df_filtered = self.df_all.query(final_query, engine=query_engine)
            self.refresh_tree(df_filtered)
            # 打印剔除条件列表
            if removed_conditions:
                print(f"[剔除的条件列表] {removed_conditions}")
                # 显示到状态栏
                self.status_var2.set(f"已剔除条件: {', '.join(removed_conditions)}")
                self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
            else:
                self.status_var2.set('')
                self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
        except Exception as e:
            log.error(f"Query error: {e}")
            self.status_var.set(f"查询错误: {e}")




    # def apply_search_python(self):
    #     val1 = self.search_var1.get().strip()
    #     val2 = self.search_var2.get().strip()

    #     if not val1 and not val2:
    #         self.status_var.set("搜索框为空")
    #         return

    #     # 构建查询语句
    #     if val1 and val2:
    #         query = f"({val1}) and ({val2})"
    #     elif val1:
    #         query = val1
    #     else:
    #         query = val2

    #     # 更新第一个搜索历史
    #     if val1:
    #         if val1 not in self.search_history1:
    #             self.search_history1.insert(0, val1)
    #             if len(self.search_history1) > 20:
    #                 self.search_history1 = self.search_history1[:20]
    #         else:
    #             self.search_history1.remove(val1)
    #             self.search_history1.insert(0, val1)
    #         self.search_combo1['values'] = self.search_history1
    #         self.save_search_history()

    #     # 更新第二个搜索历史
    #     if val2:
    #         if val2 not in self.search_history2:
    #             self.search_history2.insert(0, val2)
    #             if len(self.search_history2) > 20:
    #                 self.search_history2 = self.search_history2[:20]
    #         else:
    #             self.search_history2.remove(val2)
    #             self.search_history2.insert(0, val2)
    #         self.search_combo2['values'] = self.search_history2
    #         self.save_search_history()

    #     # 数据过滤与刷新
    #     if self.df_all.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     try:
    #         # 判断 query 是否涉及 index
    #         if 'index.' in query.lower():
    #             df_filtered = self.df_all.query(query, engine='python')
    #         else:
    #             df_filtered = self.df_all.query(query)  # 默认 engine

    #         self.refresh_tree(df_filtered)
    #         self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {query}")
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")

    # --- 搜索逻辑 ---
    # 搜索逻辑：支持双搜索框 & 独立历史
    def apply_search_nopython(self):
        val1 = self.search_var1.get().strip()
        val2 = self.search_var2.get().strip()

        if not val1 and not val2:
            self.status_var.set("搜索框为空")
            return

        # 构建查询语句
        if val1 and val2:
            query = f"({val1}) and ({val2})"
        elif val1:
            query = val1
        else:
            query = val2

        # 更新第一个搜索历史
        if val1:
            if val1 not in self.search_history1:
                self.search_history1.insert(0, val1)
                if len(self.search_history1) > 20:
                    self.search_history1 = self.search_history1[:20]
            else:
                self.search_history1.remove(val1)
                self.search_history1.insert(0, val1)
            self.search_combo1['values'] = self.search_history1
            self.save_search_history()

        # 更新第二个搜索历史
        if val2:
            if val2 not in self.search_history2:
                self.search_history2.insert(0, val2)
                if len(self.search_history2) > 20:
                    self.search_history2 = self.search_history2[:20]
            else:
                self.search_history2.remove(val2)
                self.search_history2.insert(0, val2)
            self.search_combo2['values'] = self.search_history2
            self.save_search_history()

        # 数据过滤与刷新
        if self.df_all.empty:
            self.status_var.set("当前数据为空")
            return

        try:
            df_filtered = self.df_all.query(query)
            self.refresh_tree(df_filtered)
            self.status_var.set(f"结果 {len(df_filtered)}行| 搜索: {query}")
        except Exception as e:
            log.error(f"Query error: {e}")
            self.status_var.set(f"查询错误: {e}")

    # def apply_search_start(self):
    #     query = self.search_var.get().strip()
    #     if not query:
    #         self.status_var.set("搜索框为空")
    #         return

    #     if query not in self.search_history:
    #         self.search_history.insert(0, query)
    #         if len(self.search_history) > 20:  # 最多保存20条
    #             self.search_history = self.search_history[:20]
    #         self.search_combo['values'] = self.search_history
    #         self.save_search_history()  # 保存到文件
    #     else:
    #         self.search_history.remove(query)  # リストから既存のクエリを削除する
    #         self.search_history.insert(0, query) # リストの先頭にクエリを挿入する
    #         self.search_combo['values'] = self.search_history
    #         self.save_search_history()


    #     if self.df_all.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     try:
    #         df_filtered = self.df_all.query(query)
    #         self.refresh_tree(df_filtered)
    #         self.status_var.set(f"结果 {len(df_filtered)}行| 搜索: {query}  ")
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")


    # def apply_search_src(self):
    #     query = self.search_var.get().strip()
    #     if not query:
    #         self.status_var.set("搜索框为空")
    #         return

    #     if query not in self.search_history:
    #         self.search_history.insert(0, query)
    #         if len(self.search_history) > 20:  # 最多保存20条
    #             self.search_history = self.search_history[:20]
    #         self.search_combo['values'] = self.search_history
    #         self.save_search_history()  # 保存到文件

    #     if self.current_df.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     try:
    #         df_filtered = self.current_df.query(query)
    #         self.refresh_tree(df_filtered)
    #         self.status_var.set(f"搜索: {query} | 结果 {len(df_filtered)} 行")
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")

    def clean_search(self, which):
        """清空指定搜索框内容"""
        if which == 1:
            self.search_var1.set("")
        else:
            self.search_var2.set("")

        self.select_code = None
        self.sortby_col = None
        self.sortby_col_ascend = None
        self.refresh_tree(self.df_all)
        resample = self.resample_combo.get()
        # self.status_var.set(f"搜索框 {which} 已清空")
        # self.status_var.set(f"Row 结果 {len(self.current_df)} 行 | resample: {resample} ")

    def delete_search_history(self, which, entry=None):
        """
        删除指定搜索框的历史条目
        which = 1 -> 顶部搜索框
        which = 2 -> 底部搜索框
        entry: 指定要删除的条目，如果为空则用搜索框当前内容
        """
        if which == 1:
            history = self.search_history1
            combo = self.search_combo1
            var = self.search_var1
        else:
            history = self.search_history2
            combo = self.search_combo2
            var = self.search_var2

        target = entry or var.get().strip()
        if not target:
            self.status_var.set(f"搜索框 {which} 内容为空，无可删除项")
            return

        if target in history:
            history.remove(target)
            combo['values'] = history
            self.save_search_history()
            self.status_var.set(f"搜索框 {which} 已删除历史: {target}")
            if var.get() == target:
                var.set('')
            # if select_var is not None and select_var.get() == target:
            #     select_var.set('')
        else:
            self.status_var.set(f"搜索框 {which} 历史中没有: {target}")


    # def clean_search(self, entry=None):
    #     """删除指定历史，默认删除当前搜索框内容"""
    #     self.search_var.set('')
    #     self.select_code = None
    #     self.sortby_col = None
    #     self.sortby_col_ascend = None
    #     self.refresh_tree(self.df_all)
    #     resample = self.resample_combo.get()
    #     self.status_var.set(f"Row 结果 {len(self.current_df)} 行 | resample: {resample} ")
    
    # def delete_search_history(self, entry=None):
    #     """删除指定历史，默认删除当前搜索框内容"""
    #     target = entry or self.search_var.get().strip()
    #     if target in self.search_history:
    #         self.search_history.remove(target)
    #         self.search_combo['values'] = self.search_history
    #         self.save_search_history()
    #         self.status_var.set(f"已删除历史: {target}")


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
        # blk = self.blk_label.cget("text")
        resample = self.resample_combo.get()
        # search = self.search_entry.get()
        search = self.search_var1.get()
        self.status_var.set(f"Rows: {cnt} | blkname: {self.blkname} | resample: {resample} | st: {self.st_key_sort} | search: {search}")

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
        file_name = os.path.join(DARACSV_DIR, f"monitor_{self.resample_combo.get()}_{time.strftime('%Y%m%d_%H%M')}.csv")
        self.current_df.to_csv(file_name, index=True, encoding="utf-8-sig")
        idx =file_name.find('monitor')
        status_txt = file_name[idx:]
        self.status_var2.set(f"已保存数据到 {status_txt}")

    def load_data_from_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_path:
            try:
                df = pd.read_csv(file_path, index_col=0)
                # 如果 CSV 本身已经有 code 列，不要再插入
                if 'code' in df.columns:
                    df = df.copy()
                #停止刷新
                self.stop_refresh()
                self.df_all = df
                self.refresh_tree(df)
                idx =file_path.find('monitor')
                status_txt = file_path[idx:]
                # print(f'status_txt:{status_txt}')
                self.status_var2.set(f"已加载数据: {status_txt}")
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
        archive_search_history_list()
        try:
            self.manager.shutdown()
        except Exception as e: 
            print(f'manager.shutdown : {e}')
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
    if cct.isMac():
        width, height = 100, 32
        cct.set_console(width, height)
    else:
        width, height = 100, 32
        cct.set_console(width, height)
    app.mainloop()
