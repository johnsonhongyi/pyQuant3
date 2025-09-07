import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry

# ------------------------
# 样式配置
# ------------------------
class StyleConfig:
    BG = "#F6F8FA"
    ROW_ODD = "#FFFFFF"
    ROW_EVEN = "#E9F8F0"
    TEXT_COLOR = "#222222"
    HIGHLIGHT = "#FFF8C5"
    FONT = ("Microsoft YaHei", 9)
    BTN_FONT = ("Microsoft YaHei", 10)

# ------------------------
# 主窗口类
# ------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("股票异动数据监控")
        self.geometry("750x550")
        self.minsize(720, 500)
        self.configure(bg=StyleConfig.BG)
        self.resizable(True, True)

        # 初始化属性
        self.stock_types = [
            "火箭发射", "快速反弹", "大笔买入", "封涨停板", "打开跌停板", "有大买盘", 
            "竞价上涨", "高开5日线", "向上缺口", "60日新高", "60日大幅上涨", "加速下跌", 
            "高台跳水", "大笔卖出", "封跌停板", "打开涨停板", "有大卖盘", "竞价下跌", 
            "低开5日线", "向下缺口", "60日新低", "60日大幅下跌"
        ]
        self.type_var = tk.StringVar(value="")
        self.tdx_var = tk.BooleanVar(value=True)
        self.ths_var = tk.BooleanVar(value=False)
        self.dfcf_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="就绪 | 等待操作...")

        # 样式
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Treeview", 
                             background=StyleConfig.ROW_ODD, 
                             foreground=StyleConfig.TEXT_COLOR, 
                             rowheight=25,
                             fieldbackground=StyleConfig.ROW_ODD,
                             font=StyleConfig.FONT)
        self.style.configure("Treeview.Heading", 
                             font=('Microsoft YaHei', 10, 'bold'),
                             background="#4a6984",
                             foreground="white",
                             relief="flat")
        self.style.map("Treeview", background=[('selected', '#3478bf')])

        # 创建界面
        self.create_toolbar()
        self.create_type_selection()
        self.create_search_frame()
        self.create_treeview()
        self.create_status_bar()
        self.create_context_menu()

    # ------------------------
    # 工具栏
    # ------------------------
    def create_toolbar(self):
        self.toolbar = tk.Frame(self, bg="#f0f0f0", padx=5, pady=5)
        self.toolbar.pack(fill=tk.X)

        self.refresh_btn = tk.Button(
            self.toolbar, text="↻ 刷新数据", command=self.refresh_data,
            font=StyleConfig.BTN_FONT, bg="#5b9bd5", fg="white", padx=10, pady=3, relief="flat"
        )
        self.refresh_btn.pack(side=tk.LEFT, padx=5)

        self.delete_btn = tk.Button(
            self.toolbar, text="删除选中记录", command=self.delete_selected_records,
            font=StyleConfig.BTN_FONT, bg="#d9534f", fg="white", padx=10, pady=3, relief="flat"
        )
        self.delete_btn.pack(side=tk.LEFT, padx=5)

        tk.Label(self.toolbar, text="选择日期:", font=StyleConfig.BTN_FONT, bg=self.toolbar['bg']).pack(side=tk.LEFT, padx=(10,5))
        self.date_entry = DateEntry(self.toolbar, width=12, background='darkblue', foreground='white', borderwidth=2,
                                    font=StyleConfig.FONT)
        self.date_entry.pack(side=tk.LEFT, padx=5)

        tk.Checkbutton(self.toolbar, text="联动TDX", variable=self.tdx_var, command=self.update_linkage_status).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(self.toolbar, text="联动THS", variable=self.ths_var, command=self.update_linkage_status).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(self.toolbar, text="联动DC", variable=self.dfcf_var, command=self.update_linkage_status).pack(side=tk.LEFT, padx=5)

    # ------------------------
    # 异动类型选择
    # ------------------------
    def create_type_selection(self):
        self.type_frame = tk.LabelFrame(self, text="异动类型选择", font=('Microsoft YaHei', 9), padx=10, pady=10, bg="#f9f9f9")
        self.type_frame.pack(fill=tk.X, padx=10, pady=5)
        self.radio_container = tk.Frame(self.type_frame, bg="#f9f9f9")
        self.radio_container.pack(fill=tk.X)

        buttons_per_row = 7
        for i, stock_type in enumerate(self.stock_types):
            row = i // buttons_per_row
            col = i % buttons_per_row
            btn = tk.Radiobutton(
                self.radio_container, text=stock_type, variable=self.type_var, value=stock_type,
                command=self.search_by_type, font=('Microsoft YaHei', 8), bg="#f9f9f9",
                activebackground="#e6f3ff", padx=5, pady=2
            )
            btn.grid(row=row, column=col, sticky=tk.W, padx=5, pady=3)

    # ------------------------
    # 搜索框
    # ------------------------
    def create_search_frame(self):
        self.search_frame = tk.Frame(self, bg="#f0f0f0", padx=10, pady=10)
        self.search_frame.pack(fill=tk.X, padx=10)

        tk.Label(self.search_frame, text="股票代码搜索:", font=('Microsoft YaHei', 9), bg="#f0f0f0").pack(side=tk.LEFT, padx=(0,5))
        self.code_entry = tk.Entry(self.search_frame, width=10, font=StyleConfig.FONT)
        self.code_entry.pack(side=tk.LEFT, padx=5)
        self.code_entry.bind("<KeyRelease>", self.on_code_entry_change)

        tk.Button(self.search_frame, text="搜索", command=self.search_by_code,
                  font=StyleConfig.FONT, bg="#5b9bd5", fg="white", padx=12, pady=2, relief="flat").pack(side=tk.LEFT, padx=5)
        tk.Button(self.search_frame, text="清空", command=lambda: [self.code_entry.delete(0, tk.END)],
                  font=StyleConfig.FONT, padx=10, pady=2).pack(side=tk.LEFT, padx=5)

    # ------------------------
    # Treeview
    # ------------------------
    def create_treeview(self):
        self.columns = ('时间', '代码', '名称','count', '异动类型', '涨幅', '价格', '量')
        self.tree_frame = tk.Frame(self)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))

        self.tree = ttk.Treeview(self.tree_frame, columns=self.columns, show="headings", selectmode="extended")
        self.vsb = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(self.tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        for col in self.columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=80, anchor=tk.CENTER)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        self.tree_frame.grid_rowconfigure(0, weight=1)
        self.tree_frame.grid_columnconfigure(0, weight=1)

    # ------------------------
    # 状态栏
    # ------------------------
    def create_status_bar(self):
        self.status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(5,2))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ------------------------
    # 上下文菜单
    # ------------------------
    def create_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="添加到监控", command=self.add_selected_stock)
        self.tree.bind("<Button-3>", self.show_context_menu)

    # ------------------------
    # 占位函数
    # ------------------------
    def refresh_data(self): pass
    def delete_selected_records(self): pass
    def search_by_type(self): pass
    def search_by_code(self): pass
    def update_linkage_status(self): pass
    def on_code_entry_change(self, event): pass
    def show_context_menu(self, event): pass
    def add_selected_stock(self): pass

# ------------------------
# 启动
# ------------------------
if __name__ == "__main__":
    app = App()
    app.mainloop()
