import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
import threading
import time
import random

# ------------------------
# 示例数据接口（真实接口替换此函数）
# ------------------------
def fetch_stock_data(linkage_options, date_str):
    """
    linkage_options: dict with keys 'tdx', 'ths', 'dfcf', bool values
    date_str: 日期选择器字符串
    返回示例数据列表，每行：[时间, 代码, 名称, count, 异动类型, 涨幅, 价格, 量]
    """
    stock_types = [
        "火箭发射", "快速反弹", "大笔买入", "封涨停板", "打开跌停板", "有大买盘",
        "竞价上涨", "高开5日线", "向上缺口", "60日新高", "60日大幅上涨", "加速下跌",
        "高台跳水", "大笔卖出", "封跌停板", "打开涨停板", "有大卖盘", "竞价下跌",
        "低开5日线", "向下缺口", "60日新低", "60日大幅下跌"
    ]
    data = []
    for i in range(20):
        row = [
            date_str,
            f"{100000+i}",
            f"股票{i}",
            random.randint(1,100),
            random.choice(stock_types),
            f"{random.uniform(-5,5):.2f}%",
            f"{random.uniform(10,200):.2f}",
            random.randint(1000,10000)
        ]
        data.append(row)
    return data

# ------------------------
# 主窗口类
# ------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("股票异动数据监控")
        self.geometry("750x550")
        self.minsize(720,500)
        self.resizable(True,True)

        # 属性
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
        self.style.configure("Treeview", rowheight=25, font=("Microsoft YaHei",9))
        self.style.configure("Treeview.Heading", font=("Microsoft YaHei",10,"bold"), background="#4a6984", foreground="white")

        # 创建界面
        self.create_toolbar()
        self.create_type_selection()
        self.create_search_frame()
        self.create_treeview()
        self.create_status_bar()
        self.create_context_menu()

        # 初始加载数据
        self.populate_treeview()
        # 定时刷新数据
        self.auto_refresh_interval = 300  # 5分钟
        self.after(1000, self.auto_refresh_task)

    # ------------------------
    # 工具栏
    # ------------------------
    def create_toolbar(self):
        self.toolbar = tk.Frame(self,bg="#f0f0f0", padx=5,pady=5)
        self.toolbar.pack(fill=tk.X)
        tk.Button(self.toolbar,text="↻ 刷新数据",command=self.refresh_data,bg="#5b9bd5",fg="white").pack(side=tk.LEFT,padx=5)
        tk.Button(self.toolbar,text="删除选中记录",command=self.delete_selected_records,bg="#d9534f",fg="white").pack(side=tk.LEFT,padx=5)
        tk.Label(self.toolbar,text="选择日期:").pack(side=tk.LEFT,padx=(10,5))
        self.date_entry = DateEntry(self.toolbar,width=12)
        self.date_entry.pack(side=tk.LEFT,padx=5)
        tk.Checkbutton(self.toolbar,text="联动TDX",variable=self.tdx_var,command=self.update_linkage_status).pack(side=tk.LEFT,padx=5)
        tk.Checkbutton(self.toolbar,text="联动THS",variable=self.ths_var,command=self.update_linkage_status).pack(side=tk.LEFT,padx=5)
        tk.Checkbutton(self.toolbar,text="联动DC",variable=self.dfcf_var,command=self.update_linkage_status).pack(side=tk.LEFT,padx=5)

    # ------------------------
    # 异动类型选择
    # ------------------------
    def create_type_selection(self):
        self.type_frame = tk.LabelFrame(self,text="异动类型选择",padx=10,pady=10)
        self.type_frame.pack(fill=tk.X,padx=10,pady=5)
        self.radio_container = tk.Frame(self.type_frame)
        self.radio_container.pack(fill=tk.X)
        buttons_per_row = 7
        for i, stock_type in enumerate(self.stock_types):
            row = i // buttons_per_row
            col = i % buttons_per_row
            tk.Radiobutton(self.radio_container,text=stock_type,variable=self.type_var,value=stock_type,command=self.search_by_type).grid(row=row,column=col,sticky=tk.W,padx=5,pady=3)

    # ------------------------
    # 搜索框
    # ------------------------
    def create_search_frame(self):
        self.search_frame = tk.Frame(self)
        self.search_frame.pack(fill=tk.X,padx=10)
        tk.Label(self.search_frame,text="股票代码搜索:").pack(side=tk.LEFT)
        self.code_entry = tk.Entry(self.search_frame)
        self.code_entry.pack(side=tk.LEFT,padx=5)
        self.code_entry.bind("<KeyRelease>", self.on_code_entry_change)
        tk.Button(self.search_frame,text="搜索",command=self.search_by_code,bg="#5b9bd5",fg="white").pack(side=tk.LEFT,padx=5)
        tk.Button(self.search_frame,text="清空",command=lambda:[self.code_entry.delete(0,tk.END),self.populate_treeview()]).pack(side=tk.LEFT,padx=5)

    # ------------------------
    # Treeview
    # ------------------------
    def create_treeview(self):
        self.columns = ('时间', '代码', '名称','count', '异动类型', '涨幅', '价格', '量')
        self.tree_frame = tk.Frame(self)
        self.tree_frame.pack(fill=tk.BOTH,expand=True,padx=10,pady=(0,10))
        self.tree = ttk.Treeview(self.tree_frame, columns=self.columns, show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(self.tree_frame,orient="vertical",command=self.tree.yview)
        hsb = ttk.Scrollbar(self.tree_frame,orient="horizontal",command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        for col in self.columns:
            self.tree.heading(col,text=col)
            self.tree.column(col,width=80,anchor=tk.CENTER)
        self.tree.grid(row=0,column=0,sticky="nsew")
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        self.tree_frame.grid_rowconfigure(0,weight=1)
        self.tree_frame.grid_columnconfigure(0,weight=1)
        self.tree.bind("<Button-3>",self.show_context_menu)

    # ------------------------
    # 状态栏
    # ------------------------
    def create_status_bar(self):
        self.status_bar = ttk.Label(self,textvariable=self.status_var,relief=tk.SUNKEN,anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM,fill=tk.X)

    # ------------------------
    # 上下文菜单
    # ------------------------
    def create_context_menu(self):
        self.context_menu = tk.Menu(self,tearoff=0)
        self.context_menu.add_command(label="添加到监控",command=self.add_selected_stock)

    # ------------------------
    # 异动联动
    # ------------------------
    def update_linkage_status(self):
        status=[]
        if self.tdx_var.get(): status.append("TDX")
        if self.ths_var.get(): status.append("THS")
        if self.dfcf_var.get(): status.append("DC")
        self.status_var.set("联动: "+",".join(status) if status else "无联动")

    # ------------------------
    # 刷新/删除/搜索
    # ------------------------
    def refresh_data(self):
        self.populate_treeview()
        self.status_var.set("数据已刷新")

    def delete_selected_records(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
        self.status_var.set("已删除选中记录")

    def search_by_type(self):
        selected_type = self.type_var.get()
        for iid in self.tree.get_children():
            vals = self.tree.item(iid,"values")
            if selected_type in vals:
                self.tree.selection_add(iid)
            else:
                self.tree.selection_remove(iid)
        self.status_var.set(f"按类型筛选: {selected_type}")

    def search_by_code(self):
        code = self.code_entry.get().strip()
        for iid in self.tree.get_children():
            vals = self.tree.item(iid,"values")
            if code in vals[1]:
                self.tree.selection_add(iid)
            else:
                self.tree.selection_remove(iid)
        self.status_var.set(f"按代码筛选: {code}")

    def on_code_entry_change(self,event):
        self.search_by_code()

    # ------------------------
    # 右键菜单
    # ------------------------
    def show_context_menu(self,event):
        self.context_menu.post(event.x_root,event.y_root)

    def add_selected_stock(self):
        selected = self.tree.selection()
        codes = [self.tree.item(iid,"values")[1] for iid in selected]
        messagebox.showinfo("添加监控",f"已添加到监控: {codes}")

    # ------------------------
    # 填充数据
    # ------------------------
    def populate_treeview(self):
        self.tree.delete(*self.tree.get_children())
        date_str = self.date_entry.get()
        linkage_options = {'tdx':self.tdx_var.get(),'ths':self.ths_var.get(),'dfcf':self.dfcf_var.get()}
        data = fetch_stock_data(linkage_options,date_str)
        for row in data:
            self.tree.insert("",tk.END,values=row)

    # ------------------------
    # 自动刷新任务
    # ------------------------
    def auto_refresh_task(self):
        self.populate_treeview()
        self.status_var.set("自动刷新完成")
        self.after(self.auto_refresh_interval*1000,self.auto_refresh_task)

# ------------------------
# 启动
# ------------------------
if __name__=="__main__":
    app=App()
    app.mainloop()
