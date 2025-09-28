import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd

# ===================== 模拟数据 =====================
DISPLAY_COLS = ['name', 'trade', 'boll', 'dff', 'df2', 'couts', 
                'percent', 'per1d', 'perc1d', 'ra', 'ral', 
                'topR', 'volume', 'red', 'lastdu4', 'category']

DF_ALLCOLUMNS = [
    'name', 'open', 'close', 'trade', 'high', 'low', 'volume', 'turnover',
    'boll', 'dff', 'df2', 'couts', 'percent', 'per1d', 'perc1d',
    'ra', 'ral', 'topR', 'red', 'lastdu4', 'category',
    'macd', 'ma5d', 'ma10d', 'ma20d', 'ma60d'
]

# 模拟数据
data = {
    'name': ['平安银行', '招商银行', '贵州茅台'],
    'trade': [12.3, 36.7, 1532],
    'boll': [12.1, 36.5, 1500],
    'dff': [0.3, -0.1, 1.2],
    'df2': [0.2, -0.2, 1.0],
    'couts': [100, 200, 50],
    'percent': [0.5, -0.2, 1.3],
    'per1d': [0.3, -0.1, 1.0],
    'perc1d': [0.4, -0.15, 1.1],
    'ra': [10, 20, 30],
    'ral': [5, 15, 25],
    'topR': [1, 2, 3],
    'volume': [20000, 30000, 10000],
    'red': [1, 0, 1],
    'lastdu4': [4, 5, 6],
    'category': ['银行', '银行', '白酒']
}
df = pd.DataFrame(data)


# ===================== 主应用 =====================
class StockApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("列组合管理 Demo")
        self.geometry("1000x600")

        self.current_df = df.copy()
        self.saved_col_groups = {}  # 保存的组合
        self.current_cols = ["code"] + DISPLAY_COLS

        # TreeView
        self.tree = ttk.Treeview(self, show="headings")
        self.tree.pack(fill="both", expand=True)

        self.update_treeview_cols(DISPLAY_COLS)
        self.insert_data()

        # 管理按钮
        btn = tk.Button(self, text="管理列组合", command=self.open_col_manager)
        btn.pack(pady=10)

    def insert_data(self):
        """插入模拟数据"""
        for _, row in self.current_df.iterrows():
            values = [row.get(col, "") for col in self.current_cols if col != "code"]
            self.tree.insert("", "end", values=["000001"] + values)

    def update_treeview_cols(self, new_cols):
        """更新 TreeView 的列"""
        self.current_cols = ["code"] + new_cols
        self.tree["columns"] = self.current_cols

        for col in self.current_cols:
            self.tree.heading(col, text=col)
            width = 120 if col == "name" else 80
            self.tree.column(col, width=width, anchor="center", minwidth=50)

        self.adjust_column_widths()

    def adjust_column_widths(self):
        """根据 df 内容调整列宽"""
        for col in self.current_cols:
            if col not in self.current_df.columns:
                self.tree.column(col, width=80)
                continue
            try:
                max_len = max([len(str(x)) for x in self.current_df[col].fillna("").values] + [len(col)])
            except Exception:
                max_len = len(col)
            width = min(max(max_len * 8, 60), 300)
            if col == "name":
                width = int(width * 1.6)
            self.tree.column(col, width=width)

    def open_col_manager(self):
        ColManager(self)


# ===================== 列组合管理器 =====================
class ColManager(tk.Toplevel):
    def __init__(self, app: StockApp):
        super().__init__(app)
        self.app = app
        self.title("列组合管理器")
        self.geometry("800x500")

        # 左边：所有列
        self.all_cols_lb = tk.Listbox(self, selectmode="multiple")
        for c in DF_ALLCOLUMNS:
            self.all_cols_lb.insert("end", c)
        self.all_cols_lb.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        # 右边：当前组合
        self.current_cols_lb = tk.Listbox(self, selectmode="extended")
        for c in DISPLAY_COLS:
            self.current_cols_lb.insert("end", c)
        self.current_cols_lb.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        # 操作按钮
        frame = tk.Frame(self)
        frame.pack(side="left", fill="y", padx=5)

        tk.Button(frame, text="添加 →", command=self.add_selected).pack(pady=5)
        tk.Button(frame, text="← 移除", command=self.remove_selected).pack(pady=5)
        tk.Button(frame, text="保存组合", command=self.save_group).pack(pady=5)
        tk.Button(frame, text="应用组合", command=self.apply_group).pack(pady=5)

    def add_selected(self):
        selected = [self.all_cols_lb.get(i) for i in self.all_cols_lb.curselection()]
        for col in selected:
            if col not in self.current_cols_lb.get(0, "end"):
                self.current_cols_lb.insert("end", col)

    def remove_selected(self):
        for i in reversed(self.current_cols_lb.curselection()):
            self.current_cols_lb.delete(i)

    def save_group(self):
        name = tk.simpledialog.askstring("保存组合", "请输入组合名称：")
        if not name:
            return
        cols = list(self.current_cols_lb.get(0, "end"))
        self.app.saved_col_groups[name] = cols
        messagebox.showinfo("提示", f"组合 [{name}] 已保存")

    def apply_group(self):
        cols = list(self.current_cols_lb.get(0, "end"))
        self.app.update_treeview_cols(cols)
        messagebox.showinfo("提示", "组合已应用到主视图")


if __name__ == "__main__":
    app = StockApp()
    app.mainloop()
