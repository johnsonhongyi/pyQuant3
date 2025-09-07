import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
import random
import string
import threading
from concurrent.futures import ThreadPoolExecutor
import time

# ------------------------
# 全局样式配置
# ------------------------
BG = "#F6F8FA"
TITLE_BG = "#2B2F3A"
TITLE_FG = "#FFFFFF"
ACCENT = "#4C9F70"
ROW_ODD = "#FFFFFF"
ROW_EVEN = "#E9F8F0"  # 淡绿色微光
TEXT_COLOR = "#222222"
HIGHLIGHT = "#FFF8C5"
HOVER_TITLE_BTN = "#3A3F4B"
HOVER_TITLE_CLOSE = "#E81123"

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
        
        self.after_id = None # 用于处理延迟保存的ID
        
        # 拖动、最大化/还原
        self._drag_data = {"x": 0, "y": 0}
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
        self.style.map("Hover.TButton", background=[("active", HOVER_TITLE_BTN)])

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
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=HOVER_TITLE_BTN if b != close_btn else HOVER_TITLE_CLOSE))
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
        self._drag_data = {"x": 0, "y": 0}

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
        container.pack(fill="both", expand=True, padx=12, pady=(12, 12))

        # 工具栏
        toolbar = tk.Frame(container, bg=BG)
        toolbar.pack(fill="x", pady=(0, 8))
        tk.Label(toolbar, text="Search:", bg=BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=30, style="Search.TEntry")
        search_entry.pack(side="left", padx=(8, 6))
        search_entry.bind("<KeyRelease>", lambda e: self.highlight_search())
        
        search_btn = ttk.Button(toolbar, text="搜索", style="Custom.TButton", command=self.highlight_search)
        search_btn.pack(side="left", padx=(4, 6))
        clear_btn = ttk.Button(toolbar, text="重置", style="Custom.TButton", command=self.reset_filter)
        clear_btn.pack(side="left", padx=(4, 6))
        refresh_btn = ttk.Button(toolbar, text="刷新数据", style="Custom.TButton", command=self.reload_data)
        refresh_btn.pack(side="right", padx=(4, 6))

        for btn in (search_btn, clear_btn, refresh_btn):
            btn.bind("<Enter>", lambda e, b=btn: b.configure(style="Hover.TButton"))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(style="Custom.TButton"))

        # TreeView
        tree_frame = tk.Frame(container, bg=BG)
        tree_frame.pack(fill="both", expand=True)
        cols = ("Name", "Code", "Value", "Tag")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=c, command=lambda _c=c: self.sort_by(_c, False))
            self.tree.column(c, anchor="w", minwidth=80)
        
        self.tree.tag_configure("oddrow", background=ROW_ODD)
        self.tree.tag_configure("evenrow", background=ROW_EVEN)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # 双击 & 右键
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.on_right_click)

    # ------------------------
    # 数据加载
    # ------------------------
    def reload_data(self):
        if self._loading:
            return
        
        for i in self.tree.get_children():
            self.tree.delete(i)
            
        self._insert_index = 0
        N = 4000
        # 使用线程池异步生成数据，不阻塞主线程
        self.executor.submit(self._generate_data_async, N)
        self._loading = True

    def _generate_data_async(self, N):
        """在后台线程中生成数据"""
        self._data_source = [gen_row(i) for i in range(1, N + 1)]
        self.after(10, self._chunk_insert)

    def _chunk_insert(self):
        """分块插入数据到Treeview"""
        start = self._insert_index
        end = min(start + self._chunk_size, len(self._data_source))
        
        for idx in range(start, end):
            row = self._data_source[idx]
            tag = "oddrow" if idx % 2 == 0 else "evenrow"
            self.tree.insert("", "end", values=(row[0], row[1], f"{row[2]:.2f}", row[3]), tags=(tag,))
            
        self._insert_index = end
        
        if self._insert_index < len(self._data_source):
            self.after(8, self._chunk_insert)
        else:
            self._loading = False
            self.autosize_columns()

    # ------------------------
    # 列宽自适应
    # ------------------------
    def autosize_columns(self):
        self.after(50, self._perform_autosize)

    def _perform_autosize(self):
        if not self.tree.get_children():
            return

        cols = self.tree["columns"]
        font = tkfont.nametofont("Treeview")

        for col_name in cols:
            max_width = font.measure(col_name) + 20 # 初始宽度为列头宽度
            
            for item in self.tree.get_children():
                try:
                    text = str(self.tree.item(item, "values")[cols.index(col_name)])
                    width = font.measure(text)
                    if width > max_width:
                        max_width = width
                except IndexError:
                    pass
            
            self.tree.column(col_name, width=max_width + 20)
            
    # ------------------------
    # 其他 Treeview 功能
    # ------------------------
    def on_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            item_values = self.tree.item(item_id, "values")
            messagebox.showinfo("双击", f"双击了项: {item_values}")

    def on_right_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id) # 选中右键点击的项
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="详情", command=lambda: self.show_details(item_id))
            menu.add_command(label="复制", command=lambda: self.copy_item(item_id))
            menu.tk_popup(event.x_root, event.y_root)

    def show_details(self, item_id):
        item_values = self.tree.item(item_id, "values")
        messagebox.showinfo("详情", f"选中项的详情: {item_values}")

    def copy_item(self, item_id):
        item_values = self.tree.item(item_id, "values")
        self.clipboard_clear()
        self.clipboard_append(", ".join(map(str, item_values)))
        messagebox.showinfo("复制", "已复制到剪贴板")

    # ------------------------
    # 搜索和过滤
    # ------------------------
    def highlight_search(self):
        query = self.search_var.get().lower()
        self.reset_filter()
        
        if not query:
            return
        
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            if any(query in str(v).lower() for v in values):
                current_tags = self.tree.item(item, "tags")
                self.tree.item(item, tags=current_tags + ("highlight",))
        
        self.tree.tag_configure("highlight", background=HIGHLIGHT)

    def reset_filter(self):
        self.search_var.set("")
        for item in self.tree.get_children():
            current_tags = self.tree.item(item, "tags")
            new_tags = tuple(t for t in current_tags if t != "highlight")
            self.tree.item(item, tags=new_tags)
        
        # 重新应用奇偶行颜色
        for idx, item in enumerate(self.tree.get_children()):
            tag = "oddrow" if idx % 2 == 0 else "evenrow"
            self.tree.item(item, tags=tag)
            
    def sort_by(self, col, reverse):
        """列排序"""
        data = [(self.tree.set(item, col), item) for item in self.tree.get_children('')]
        
        # 针对数值列进行特殊处理
        if col == "Value":
            data.sort(key=lambda x: float(x[0]), reverse=reverse)
        else:
            data.sort(reverse=reverse)
            
        for index, (val, item) in enumerate(data):
            self.tree.move(item, '', index)
            tag = "oddrow" if index % 2 == 0 else "evenrow"
            self.tree.item(item, tags=tag)
        
        # 切换排序方向
        self.tree.heading(col, command=lambda _c=col: self.sort_by(_c, not reverse))

# ------------------------
# 运行
# ------------------------
if __name__ == "__main__":
    root = App()
    root.mainloop()
