# -*- coding:utf-8 -*-
import gc
import sys
import time
import pandas as pd
import multiprocessing as mp
import tkinter as tk
from tkinter import ttk

from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import LoggerFactory, commonTips as cct
from JSONData import stockFilter as stf
from JSONData import tdx_data_Day as tdd

DISPLAY_COLS = ['code'] + ct.get_Duration_format_Values(
    ct.Monitor_format_trade,
    ['name','trade','boll','dff','df2','couts','percent','volume','category']
)

# ------------------ 后台数据进程 ------------------ #
def fetch_and_process(queue, blkname="boll", resample="d"):
    lastpTDX_DF, top_all = pd.DataFrame(), pd.DataFrame()
    st_key_sort = cct.GlobalValues().getkey("market_value") or "1"
    while True:
        try:
            top_now = tdd.getSinaAlldf(vol=ct.json_countVol, vtype=ct.json_countType)
            if top_now.empty:
                LoggerFactory.log.debug("no data fetched")
                time.sleep(ct.duration_sleep_time)
                continue

            if top_all.empty:
                if lastpTDX_DF.empty:
                    top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl=ct.duration_date_day, resample=resample)
                else:
                    top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF)
            else:
                top_all = cct.combine_dataFrame(top_all, top_now, col="couts", compare="dff")

            # 计算指标
            top_all = calc_indicators(top_all, resample)

            # 排序列初始化
            sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort)

            # 过滤
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
            top_temp = top_temp.loc[:, ct.get_Duration_format_Values(ct.Monitor_format_trade, ['name','trade','boll','dff','df2','couts','percent','volume','category'])]
            top_temp.insert(0, 'code', top_temp.index)

            queue.put(top_temp)
            gc.collect()
            time.sleep(ct.duration_sleep_time)
        except Exception as e:
            LoggerFactory.log.error(f"Error in background process: {e}", exc_info=True)
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
class StockMonitorApp(tk.Tk):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue
        self.title("Stock Monitor")
        # self.geometry("1400x700")
        self.geometry("1000x600")

        # # ------------------ Toolbar & Checkbuttons ------------------ #
        # toolbar = tk.Frame(self, bg="#f0f0f0", padx=2, pady=2)
        # toolbar.pack(fill=tk.X)
        # ------------------ Controls ------------------ #
        ctrl_frame = tk.Frame(self)
        ctrl_frame.pack(fill="x", padx=5, pady=2)

        # Right frame for Checkbuttons
        frame_right = tk.Frame(ctrl_frame, bg="#f0f0f0")
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



        tk.Label(ctrl_frame, text="blkname:").pack(side="left")
        self.blk_label = tk.Label(ctrl_frame, text=cct.GlobalValues().getkey("blkname") or "boll")
        self.blk_label.pack(side="left", padx=2)

        tk.Label(ctrl_frame, text="resample:").pack(side="left", padx=5)
        self.resample_combo = ttk.Combobox(ctrl_frame, values=["d","w","m"], width=5)
        self.resample_combo.set(cct.GlobalValues().getkey("resample") or "d")
        self.resample_combo.pack(side="left")
        self.resample_combo.bind("<<ComboboxSelected>>", self.set_resample)

        tk.Label(ctrl_frame, text="Search:").pack(side="left", padx=5)
        self.search_entry = tk.Entry(ctrl_frame, width=30)
        self.search_entry.pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="Go", command=self.set_search).pack(side="left", padx=2)

        # ------------------ 状态栏 ------------------ #
        self.status_var = tk.StringVar()
        self.status_bar = tk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_bar.pack(fill="x", side="bottom")

        # ------------------ TreeView ------------------ #
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=DISPLAY_COLS, show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        for col in DISPLAY_COLS:
            self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
            self.tree.column(col, width=100, anchor="center", minwidth=50)

        # Tree selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.current_df = pd.DataFrame()
        self.after(500, self.update_tree)

        self.sender = StockSender(self.tdx_var, self.ths_var, self.dfcf_var, callback=self.update_send_status)

    # ------------------ Tree 行选择 ------------------ #
    def on_tree_select(self, event):
        selected_item = self.tree.selection()
        if selected_item:
            stock_info = self.tree.item(selected_item, 'values')
            stock_code = stock_info[0]
            stock_code = str(stock_code).zfill(6)
            LoggerFactory.log.info(f'stock_code:{stock_code}')
            # send_to_tdx(stock_code)   # 根据你的逻辑发送到 TDX 或其他
            print(f"选中股票代码: {stock_code}")
            if stock_code:
                self.sender.send(stock_code)

    # def on_tree_select(self, event):
    #     selected_item = self.tree.selection()
    #     if selected_item:
    #         stock_code = self.tree.item(selected_item, 'values')[0]
    #         self.sender.send(stock_code)

    def update_send_status(self, status_dict):
        # 更新状态栏
        status_text = f"TDX: {status_dict['TDX']} | THS: {status_dict['THS']} | DC: {status_dict['DC']}"
        self.status_var.set(status_text)

    # ------------------ Checkbutton 回调 ------------------ #
    def update_linkage_status(self):
        print(f"TDX: {self.tdx_var.get()}, THS: {self.ths_var.get()}, DC: {self.dfcf_var.get()}, "
              f"Uniq: {self.uniq_var.get()}, Sub: {self.sub_var.get()}")

    # ------------------ Tree 刷新 ------------------ #
    def refresh_tree(self, df):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for _, row in df.iterrows():
            self.tree.insert("", "end", values=list(row))
        self.current_df = df
        self.adjust_column_widths()
        self.update_status()

    # ------------------ 调整列宽 ------------------ #
    # def adjust_column_widths_0(self):
    #     for col in DISPLAY_COLS:
    #         if col in self.current_df.columns:
    #             max_len = max([len(str(val)) for val in self.current_df[col]] + [len(col)])
    #             width = min(max(max_len * 10, 60), 300)
    #             self.tree.column(col, width=width)

    # ----------------- TreeView 列宽自适应 ----------------- #
    def adjust_column_widths(self):
        for col in ["code"] + DISPLAY_COLS:
            max_width = 50  # 最小宽度
            for item in self.tree.get_children():
                cell_value = str(self.tree.set(item, col))
                # 计算字符宽度，name 列比其他列宽 1.5 倍
                factor = 1.8 if col == "name" else 1.0
                width = int(len(cell_value) * 7 * factor)
                if width > max_width:
                    max_width = width
            self.tree.column(col, width=max_width, minwidth=50)


    # ------------------ 排序 ------------------ #
    def sort_by_column(self, col, reverse):
        if col not in self.current_df.columns:
            return
        df_sorted = self.current_df.sort_values(by=col, ascending=not reverse)
        self.refresh_tree(df_sorted)
        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))

    # ------------------ 搜索 ------------------ #
    def set_search(self):
        query = self.search_entry.get().strip()
        if query and not self.current_df.empty:
            try:
                df_filtered = self.current_df.query(query)
                self.refresh_tree(df_filtered)
            except Exception as e:
                LoggerFactory.log.error(f"Query error: {e}")

    # ------------------ Resample ------------------ #
    def set_resample(self, event=None):
        val = self.resample_combo.get().strip()
        if val:
            cct.GlobalValues().setkey("resample", val)

    # ------------------ 状态栏 ------------------ #
    def update_status(self):
        cnt = len(self.current_df)
        blk = self.blk_label.cget("text")
        resample = self.resample_combo.get()
        search = self.search_entry.get()
        self.status_var.set(f"Rows: {cnt} | blkname: {blk} | resample: {resample} | search: {search}")

    # ------------------ 数据更新 ------------------ #
    def update_tree(self):
        try:
            while not self.queue.empty():
                df = self.queue.get_nowait()
                self.refresh_tree(df)
        except Exception as e:
            LoggerFactory.log.error(f"Error updating tree: {e}", exc_info=True)
        finally:
            self.after(1000, self.update_tree)

# ------------------ 主程序 ------------------ #
if __name__ == "__main__":
    LoggerFactory.log.setLevel(LoggerFactory.DEBUG)
    queue = mp.Queue()
    p = mp.Process(target=fetch_and_process, args=(queue,"boll","d"))
    p.daemon = True
    p.start()

    app = StockMonitorApp(queue)
    app.mainloop()
