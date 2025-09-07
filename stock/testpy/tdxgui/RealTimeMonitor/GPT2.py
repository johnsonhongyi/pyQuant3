import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
import random
import string
from concurrent.futures import ThreadPoolExecutor

# ------------------------
# 全局样式
# ------------------------
BG = "#F6F8FA"
TITLE_BG = "#2B2F3A"
TITLE_FG = "#FFFFFF"
ACCENT = "#4C9F70"
ROW_ODD = "#FFFFFF"
ROW_EVEN = "#E9F8F0"  # 淡绿色微光
TEXT_COLOR = "#222222"
HIGHLIGHT = "#FFF8C5"

# ------------------------
# 假数据生成（示例用）
# ------------------------
def gen_row(i):
    name = f"Item {i}"
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    value = round(random.uniform(1, 1000), 2)
    tag = random.choice(["A", "B", "C"])
    return (name, code, value, tag)

# ------------------------
# 主界面类
# ------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CleanTree Modern Fixed")
        self.overrideredirect(True)
        self.geometry("900x560+120+120")
        self.configure(bg=BG)

        # 拖动偏移
        self._drag_data = {"x":0,"y":0}
        self._is_max = False
        self._restore_geom = None

        # ttk 样式
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        # Treeview 样式
        self.style.configure("Treeview",
                             background=ROW_ODD,
                             fieldbackground=ROW_ODD,
                             foreground=TEXT_COLOR,
                             rowheight=28,
                             font=("Segoe UI", 10))
        self.style.map("Treeview", background=[("selected", ACCENT)])
        # Button 样式
        self.style.configure("Custom.TButton",
                             background=TITLE_BG,
                             foreground=TITLE_FG,
                             relief="flat",
                             font=("Segoe UI", 9, "bold"))
        self.style.configure("Search.TEntry", fieldbackground="#FFFFFF", foreground="#000000")

        # 初始化 UI
        self.create_titlebar()
        self.create_body()

        # ESC 退出
        self.bind("<Escape>", lambda e: self.destroy())

        # 数据加载
        self._data_source = []
        self._insert_index = 0
        self._chunk_size = 200
        self._loading = False
        self.executor = ThreadPoolExecutor(max_workers=2)

        self.reload_data()

    # ------------------------
    # 自定义标题栏
    # ------------------------
    def create_titlebar(self):
        titlebar = tk.Frame(self, bg=TITLE_BG, height=36)
        titlebar.pack(fill="x", side="top")
        lbl = tk.Label(titlebar, text="  CleanTree Modern Fixed", bg=TITLE_BG, fg=TITLE_FG,
                       font=("Segoe UI", 10, "bold"))
        lbl.pack(side="left", padx=6)

        btn_frame = tk.Frame(titlebar, bg=TITLE_BG)
        btn_frame.pack(side="right", padx=6)
        min_btn = tk.Button(btn_frame, text="—", bg=TITLE_BG, fg=TITLE_FG,
                            bd=0, relief="flat", command=self.iconify,
                            font=("Segoe UI", 12))
        min_btn.pack(side="right", padx=4)
        close_btn = tk.Button(btn_frame, text="✕", bg=TITLE_BG, fg=TITLE_FG,
                              bd=0, relief="flat", command=self.destroy,
                              font=("Segoe UI", 11))
        close_btn.pack(side="right", padx=4)

        # hover效果
        for btn in (min_btn, close_btn):
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#3A3F4B"))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=TITLE_BG))

        for w in (titlebar, lbl):
            w.bind("<ButtonPress-1>", self.start_move)
            w.bind("<ButtonRelease-1>", self.stop_move)
            w.bind("<B1-Motion>", self.on_move)
        titlebar.bind("<Double-Button-1>", self.toggle_max_restore)

    def start_move(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def stop_move(self, event):
        self._drag_data = {"x":0,"y":0}

    def on_move(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.geometry(f"+{x}+{y}")

    def toggle_max_restore(self, event=None):
        if not self._is_max:
            self._restore_geom = self.geometry()
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            self.geometry(f"{screen_w}x{screen_h}+0+0")
            self._is_max = True
        else:
            if self._restore_geom:
                self.geometry(self._restore_geom)
            self._is_max = False

    # ------------------------
    # 主体内容
    # ------------------------
    def create_body(self):
        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True, padx=12, pady=(12,12))

        # 工具栏
        toolbar = tk.Frame(container, bg=BG)
        toolbar.pack(fill="x", pady=(0,8))
        tk.Label(toolbar, text="Search:", bg=BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=30, style="Search.TEntry")
        search_entry.pack(side="left", padx=(8,6))
        search_entry.bind("<KeyRelease>", lambda e: self.highlight_search())
        search_btn = ttk.Button(toolbar, text="搜索", style="Custom.TButton", command=self.highlight_search)
        search_btn.pack(side="left", padx=(4,6))
        clear_btn = ttk.Button(toolbar, text="重置", style="Custom.TButton", command=self.reset_filter)
        clear_btn.pack(side="left", padx=(4,6))
        refresh_btn = ttk.Button(toolbar, text="刷新数据", style="Custom.TButton", command=self.reload_data)
        refresh_btn.pack(side="right", padx=(4,6))

        # hover效果
        for btn in (search_btn, clear_btn, refresh_btn):
            btn.bind("<Enter>", lambda e,b=btn: b.configure(style="Hover.TButton"))
            btn.bind("<Leave>", lambda e,b=btn: b.configure(style="Custom.TButton"))

        # TreeView
        tree_frame = tk.Frame(container, bg=BG)
        tree_frame.pack(fill="both", expand=True)
        cols = ("Name","Code","Value","Tag")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=c, command=lambda _c=c: self.sort_by(_c, False))
            self.tree.column(c, anchor="w", minwidth=80, width=160)
        self.tree.tag_configure("oddrow", background=ROW_ODD)
        self.tree.tag_configure("evenrow", background=ROW_EVEN)
        self.tree.grid(row=0,column=0,sticky="nsew")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0,column=1,sticky="ns")
        hsb.grid(row=1,column=0,sticky="ew")
        tree_frame.rowconfigure(0,weight=1)
        tree_frame.columnconfigure(0,weight=1)

        # 双击 & 右键
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.on_right_click)

    # ------------------------
    # 数据加载
    # ------------------------
    def reload_data(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._insert_index = 0
        N = 4000
        self._data_source = [gen_row(i) for i in range(1,N+1)]
        self._loading = True
        self.after(10, self._chunk_insert)

    def _chunk_insert(self):
        start = self._insert_index
        end = min(start+self._chunk_size, len(self._data_source))
        for idx in range(start,end):
            row = self._data_source[idx]
            tag = "oddrow" if idx%2==0 else "evenrow"
            self.tree.insert("", "end", values=(row[0],row[1],f"{row[2]:.2f}",row[3]), tags=(tag,))
        self._insert_index = end
        if self._insert_index < len(self._data_source):
            self.after(8,self._chunk_insert)
        else:
            self._loading = False
            self.autosize_columns()

    # ------------------------
    # 列宽自适应
    # ------------------------
    def autosize_columns(self):
        for col in self.tree["columns"]:
            max_w = 60
            hdr = col
            w = tkfont.Font(font=("Segoe UI",10,"bold")).measure(hdr)+18
            max_w = max(max_w,w)
            children = self.tree.get_children()
            sample = children[:200] if len(children)>200 else children
            f = tkfont.Font(font=("Segoe UI",10))
            for iid in sample:
                val = str(self.tree.set(iid,col))
                w = f.measure(val)+18
                if w>max_w: max_w=w
            self.tree.column(col,width=min(max_w,600))

    # ------------------------
    # 搜索高亮
    # ------------------------
    def highlight_search(self, event=None):
        q = self.search_var.get().strip().lower()
        for iid in self.tree.get_children():
            vals = self.tree.item(iid,"values")
            if any(q in str(v).lower() for v in vals) and q!="":
                self.tree.item(iid, tags=("highlight",))
            else:
                tag = "oddrow" if int(iid[1:],16)%2==0 else "evenrow"
                self.tree.item(iid, tags=(tag,))
        self.tree.tag_configure("highlight", background=HIGHLIGHT)

    def reset_filter(self):
        self.search_var.set("")
        for iid in self.tree.get_children():
            tag = "oddrow" if int(iid[1:],16)%2==0 else "evenrow"
            self.tree.item(iid, tags=(tag,))

    # ------------------------
    # 双击事件
    # ------------------------
    def on_double_click(self, event):
        item = self.tree.selection()
        if item:
            vals = self.tree.item(item[0],"values")
            messagebox.showinfo("详情", f"Name:{vals[0]}\nCode:{vals[1]}\nValue:{vals[2]}\nTag:{vals[3]}")

    # ------------------------
    # 右键菜单
    # ------------------------
    def on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="复制", command=lambda:self.copy_item(iid))
            menu.add_command(label="删除", command=lambda:self.tree.delete(iid))
            menu.tk_popup(event.x_root,event.y_root)

    def copy_item(self, iid):
        vals = self.tree.item(iid,"values")
        s = "\t".join(str(v) for v in vals)
        self.clipboard_clear()
        self.clipboard_append(s)
        messagebox.showinfo("已复制", s)

    # ------------------------
    # 列排序
    # ------------------------
    def sort_by(self, col, descending):
        data = [(self.tree.set(k,col),k) for k in self.tree.get_children('')]
        try:
            data.sort(key=lambda t: float(t[0]), reverse=descending)
        except ValueError:
            data.sort(reverse=descending)
        for idx,(val,k) in enumerate(data):
            self.tree.move(k,'',idx)
        self.tree.heading(col, command=lambda:_col_sort(col, not descending))

def _col_sort(col,desc):
    app.sort_by(col,desc)

# ------------------------
# 启动
# ------------------------
if __name__=="__main__":
    app = App()
    app.mainloop()
