import tkinter as tk
from tkinter import ttk, Menu

DISPLAY_COLS = ["name", "trade", "percent", "volume"]  # 默认显示的列

class StockMonitorApp(tk.Tk):
    def __init__(self, df_all):
        super().__init__()
        self.title("股票监控")
        self.df_all = df_all  # 保存全量数据

        # 初始化列
        self.current_cols = ["code"] + DISPLAY_COLS
        self.tree = ttk.Treeview(self, columns=self.current_cols, show="headings")
        self.tree.pack(fill="both", expand=True)

        for col in self.current_cols:
            self.tree.heading(col, text=col, anchor="center")
            self.tree.column(col, width=100, anchor="center")

            # 绑定右键菜单
            self.tree.heading(col, text=col, anchor="center")
            self.tree.heading(col, command=lambda c=col: self.show_column_menu(c))

        # 初次刷新
        self.refresh_tree_data()

    # def show_column_menu(self, col):
    #     """表头右键菜单"""
    #     menu = Menu(self, tearoff=0)

    #     for new_col in self.df_all.columns:
    #         if new_col not in self.current_cols:  # 避免重复
    #             menu.add_command(
    #                 label=f"替换为 {new_col}",
    #                 command=lambda nc=new_col, oc=col: self.replace_column(oc, nc)
    #             )

    #     menu.post(self.winfo_pointerx(), self.winfo_pointery())
    def show_column_menu1(self, col):
        """表头点击后弹出列替换菜单"""
        menu = Menu(self, tearoff=0)

        # 显示 df_all 所有列（除了已经在 current_cols 的）
        for new_col in self.df_all.columns:
            if new_col not in self.current_cols:
                menu.add_command(
                    label=f"替换 {col} → {new_col}",
                    command=lambda nc=new_col, oc=col: self.replace_column(oc, nc)
                )

        # 弹出菜单
        menu.post(self.winfo_pointerx(), self.winfo_pointery())

    def show_column_menu(self, col):
        # 弹出一个 Toplevel 网格窗口显示 df_all 的列，点击即可替换
        win = tk.Toplevel(self)
        win.transient(self)  # 弹窗在父窗口之上
        win.grab_set()
        win.title(f"替换列: {col}")

        # 过滤掉已经在 current_cols 的列
        all_cols = [c for c in self.df_all.columns if c not in self.current_cols or c == col]

        # 网格排列参数
        cols_per_row = 5  # 每行显示5个按钮，可根据需要调整
        btn_width = 15
        btn_height = 1

        for i, c in enumerate(all_cols):
            btn = tk.Button(win,
                            text=c,
                            width=btn_width,
                            height=btn_height,
                            command=lambda nc=c, oc=col: [self.replace_column(oc, nc), win.destroy()])
            btn.grid(row=i // cols_per_row, column=i % cols_per_row, padx=2, pady=2)

    def replace_column(self, old_col, new_col):
        """替换显示列并刷新表格"""
        if old_col in self.current_cols:
            idx = self.current_cols.index(old_col)
            self.current_cols[idx] = new_col

            # 重新设置 tree 的列集合
            # new_columns = ["code"] + self.current_cols
            new_columns = self.current_cols
            self.tree.config(columns=new_columns)

            # 重新设置表头
            for col in new_columns:
                self.tree.heading(col, text=col, anchor="center",
                                  command=lambda c=col: self.show_column_menu(c))

            # 重新加载数据
            print(f'new_columns : {new_columns} DISPLAY_COLS : {DISPLAY_COLS}')
            self.refresh_tree_data()
   

    def refresh_tree_data1(self):
        """刷新表格数据"""
        for i in self.tree.get_children():
            self.tree.delete(i)

        if self.df_all.empty:
            return

        for _, row in self.df_all.iterrows():
            values = [row.get(col, "") for col in self.current_cols]
            self.tree.insert("", "end", values=values)

    def refresh_tree_data(self):
        """刷新 TreeView，保证列和数据严格对齐。"""
        # 清空
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        # 若 df 为空，更新状态并返回
        if  self.df_all.empty:
            # self.current_df = pd.DataFrame() if df is None else df
            # self.update_status()
            return

        df = self.df_all.copy()

        # 确保 code 列存在并为字符串（便于显示）
        if 'code' not in df.columns:
            # 将 index 转成字符串放到 code 列
            df.insert(0, 'code', df.index.astype(str))

        # 要显示的列顺序（把 DISPLAY_COLS 的顺序保持一致）
        cols_to_show = ['code'] + [c for c in DISPLAY_COLS if c != 'code']

        # 如果 Treeview 的 columns 与我们想要的不一致，则重新配置
        current_cols = list(self.tree["columns"])
        print(f'current_cols : {current_cols} cols_to_show : {cols_to_show}')
        if current_cols != cols_to_show:
            # 关键：更新 columns，确保使用 list/tuple（不要使用 numpy array）
            self.tree.config(columns=cols_to_show)
            # 强制只显示 headings（隐藏 #0），并设置 displaycolumns 显示顺序
            self.tree.configure(show='headings')
            self.tree["displaycolumns"] = cols_to_show
            print(f'cols_to_show : {cols_to_show}')
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

        for _, row in self.df_all.iterrows():
            values = [row.get(col, "") for col in self.current_cols]
            self.tree.insert("", "end", values=values)

        # 保存完整数据（方便后续 query / 显示切换）
        # self.current_df = df
        # 调整列宽
        self.adjust_column_widths()
        # 更新状态栏
        # self.update_status()


    def adjust_column_widths(self):
        """根据当前 self.current_df 和 tree 的列调整列宽（只作用在 display 的列）"""
        cols = list(self.tree["columns"])
        # 遍历显示列并设置合适宽度
        print(f'cols: {cols} self.tree["columns"] : {self.tree["columns"]}')
        for col in cols:
            # 跳过不存在于 df 的列

            if col not in self.df_all.columns:
                # 仍要确保列有最小宽度
                print(f'col: {col}')
                self.tree.column(col, width=80)
                continue
            # 计算列中最大字符串长度
            try:
                max_len = max([len(str(x)) for x in self.current_df[col].fillna("").values] + [len(col)])
            except Exception:
                max_len = len(col)
            width = min(max(max_len * 8, 60), 400)  # 经验值：每字符约8像素，可调整
            if col == 'name':
                width = int(width * 1.6)
            self.tree.column(col, width=width)

    # def update_status(self):
    #     cnt = len(self.df_all)
    #     blk = self.blk_label.cget("text")
    #     resample = self.resample_combo.get()
    #     # search = self.search_entry.get()
    #     search = self.search_var.get()
    #     self.status_var.set(f"Rows: {cnt} | blkname: {blk} | resample: {resample} | search: {search}")

# 测试用 DataFrame
import pandas as pd
df_all = pd.DataFrame([
    {"code": "600000", "name": "浦发银行", "trade": 10.5, "percent": 2.3, "volume": 12300, "industry": "银行"},
    {"code": "600519", "name": "贵州茅台", "trade": 1800, "percent": -1.2, "volume": 8900, "industry": "白酒"},
])

if __name__ == "__main__":
    app = StockMonitorApp(df_all)
    app.mainloop()
