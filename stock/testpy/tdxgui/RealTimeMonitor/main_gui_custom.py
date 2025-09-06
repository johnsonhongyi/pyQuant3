import tkinter as tk
from tkinter import ttk
import random
import string
import time

import tkinter.font as tkfont  

# -------------------------
# 颜色与样式配置（可自定义）
# -------------------------
BG = "#F6F8FA"
TITLE_BG = "#2B2F3A"
TITLE_FG = "#FFFFFF"
ACCENT = "#4C9F70"         # 按钮、选中行颜色
ROW_ODD = "#FFFFFF"
ROW_EVEN = "#F7FBF8"
TEXT_COLOR = "#222222"

# -------------------------
# 小工具：生成假数据（演示用）
# -------------------------
def gen_row(i):
    name = "Item " + str(i)
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    value = round(random.uniform(1, 1000), 2)
    tag = random.choice(["A", "B", "C"])
    return (name, code, value, tag)

# -------------------------
# 主界面类
# -------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()

        # 无边框窗口，自行绘制标题栏
        self.overrideredirect(True)
        self.geometry("900x560+120+120")
        self.configure(bg=BG)

        # 设置样式
        style = ttk.Style(self)
        style.theme_use("clam")  # "clam" 比较好自定义
        style.configure("Treeview",
                        background=ROW_ODD,
                        foreground=TEXT_COLOR,
                        rowheight=26,
                        fieldbackground=ROW_ODD,
                        font=("Segoe UI", 10))
        style.map("Treeview", background=[("selected", ACCENT)])
        style.configure("Custom.TButton",
                        background=TITLE_BG, foreground=TITLE_FG,
                        relief="flat", font=("Segoe UI", 9, "bold"))
        style.configure("Search.TEntry", fieldbackground="#FFFFFF")

        # 保存被拖动的偏移
        self._drag_data = {"x": 0, "y": 0}

        # 顶部自定义标题栏
        self.create_titlebar()

        # 主体内容
        self.create_body()

        # 绑定 Esc 退出
        self.bind("<Escape>", lambda e: self.destroy())

    # -------------------------
    # 标题栏（可拖动、最小化、关闭）
    # -------------------------
    def create_titlebar(self):
        titlebar = tk.Frame(self, bg=TITLE_BG, relief="raised", bd=0, height=36)
        titlebar.pack(fill="x", side="top")

        # 左侧应用名
        lbl = tk.Label(titlebar, text="  CleanTree - 示例", bg=TITLE_BG, fg=TITLE_FG,
                       font=("Segoe UI", 10, "bold"))
        lbl.pack(side="left", padx=6)

        # 右侧按钮
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

        # 标题栏拖动
        for widget in (titlebar, lbl):
            widget.bind("<ButtonPress-1>", self.start_move)
            widget.bind("<ButtonRelease-1>", self.stop_move)
            widget.bind("<B1-Motion>", self.on_move)

        # 双击最大化 / 还原（简单实现）
        titlebar.bind("<Double-Button-1>", self.toggle_max_restore)
        self._is_max = False
        self._restore_geom = None

    def start_move(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def stop_move(self, event):
        self._drag_data["x"] = 0
        self._drag_data["y"] = 0

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

    # -------------------------
    # 主体：搜索栏 + Treeview
    # -------------------------
    def create_body(self):
        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True, padx=12, pady=(12, 12))

        # 顶部工具栏（搜索、刷新）
        toolbar = tk.Frame(container, bg=BG)
        toolbar.pack(fill="x", pady=(0, 8))

        tk.Label(toolbar, text="Search:", bg=BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=30, style="Search.TEntry")
        search_entry.pack(side="left", padx=(8, 6))
        search_entry.bind("<Return>", lambda e: self.filter_tree())

        search_btn = ttk.Button(toolbar, text="搜索", style="Custom.TButton", command=self.filter_tree)
        search_btn.pack(side="left", padx=(4, 6))

        clear_btn = ttk.Button(toolbar, text="重置", style="Custom.TButton", command=self.reset_filter)
        clear_btn.pack(side="left", padx=(4, 6))

        refresh_btn = ttk.Button(toolbar, text="刷新数据", command=self.reload_data)
        refresh_btn.pack(side="right", padx=(4, 6))

        # Tree + Scrollbars
        tree_frame = tk.Frame(container, bg=BG)
        tree_frame.pack(fill="both", expand=True)

        cols = ("Name", "Code", "Value", "Tag")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=c, command=lambda _c=c: self.sort_by(_c, False))
            # 固定最小宽度，可按需调整
            self.tree.column(c, anchor="w", minwidth=80, width=160)

        # 交替行颜色 via tags
        self.tree.tag_configure("oddrow", background=ROW_ODD)
        self.tree.tag_configure("evenrow", background=ROW_EVEN)
        self.tree.tag_configure("selected", background=ACCENT)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # 双击与右键菜单
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.on_right_click)  # 右键

        # 用于批量插入的控制
        self._data_source = []      # 源数据列表
        self._insert_index = 0      # 分批插入的指针
        self._chunk_size = 200      # 每次插入数量（可调）
        self._loading = False

        # 初次加载示例数据
        self.reload_data()

    # -------------------------
    # 加载 / 过滤 / 刷新
    # -------------------------
    def reload_data(self):
        # 清空现有
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._insert_index = 0
        # 生成较多示例数据（演示性能）
        N = 4000
        self._data_source = [gen_row(i) for i in range(1, N+1)]
        # 启动分批插入
        self._loading = True
        self.after(10, self._chunk_insert)

    def _chunk_insert(self):
        """分批插入数据，避免主线程长时间阻塞"""
        start = self._insert_index
        end = min(start + self._chunk_size, len(self._data_source))
        for idx in range(start, end):
            row = self._data_source[idx]
            tag = "oddrow" if (idx % 2 == 0) else "evenrow"
            # 插入时把数值格式化成字符串，减少运行时计算
            self.tree.insert("", "end", values=(row[0], row[1], f"{row[2]:.2f}", row[3]), tags=(tag,))
        self._insert_index = end
        if self._insert_index < len(self._data_source):
            # 继续下一块（yield 控制权回主循环）
            self.after(8, self._chunk_insert)
        else:
            self._loading = False
            # 载入完成后自适应列宽（可选）
            self.autosize_columns()

    def autosize_columns(self):
        """根据内容调整列宽（只做简单的宽度测量）"""
        for col in self.tree["columns"]:
            max_w = 60  # 最小宽度
            # 计算 header 宽度
            hdr = col
            w = tk.font.Font(font=("Segoe UI", 10, "bold")).measure(hdr) + 18
            max_w = max(max_w, w)
            # 查看部分行（不必遍历全部加快速度）
            children = self.tree.get_children()
            sample = children[:200] if len(children) > 200 else children
            f = tk.font.Font(font=("Segoe UI", 10))
            for iid in sample:
                val = str(self.tree.set(iid, col))
                w = f.measure(val) + 18
                if w > max_w:
                    max_w = w
            self.tree.column(col, width=min(max_w, 600))

    def filter_tree(self):
        q = self.search_var.get().strip().lower()
        if not q:
            self.reset_filter()
            return
        # 简单过滤：按 Name 或 Code 或 Tag
        # 为了简单和较快，直接遍历数据源并重建 tree（可优化成索引）
        filtered = []
        for row in self._data_source:
            if q in str(row[0]).lower() or q in str(row[1]).lower() or q in str(row[3]).lower():
                filtered.append(row)
        # 重建 tree（分批插入）
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._insert_index = 0
        self._loading = True
        self._data_source_filtered = filtered
        # 切换数据源临时指向 filtered 并插入
        self._orig_data_source = self._data_source
        self._data_source = filtered
        self.after(10, self._chunk_insert)

    def reset_filter(self):
        # 如果之前过滤过，恢复
        if hasattr(self, "_orig_data_source") and self._orig_data_source is not None:
            self._data_source = self._orig_data_source
            self._orig_data_source = None
        self.search_var.set("")
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._insert_index = 0
        self._loading = True
        self.after(10, self._chunk_insert)

    # -------------------------
    # 交互：双击、右键、排序
    # -------------------------
    def on_double_click(self, event):
        iid = self.tree.focus()
        if not iid:
            return
        vals = self.tree.item(iid, "values")
        tk.messagebox.showinfo("详细信息", f"Name: {vals[0]}\nCode: {vals[1]}\nValue: {vals[2]}\nTag: {vals[3]}")

    def on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            # 选中当前行
            self.tree.selection_set(iid)
            # 构建菜单
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="复制代码", command=lambda: self.copy_code(iid))
            menu.add_command(label="详情", command=lambda: self.show_details(iid))
            menu.add_separator()
            menu.add_command(label="删除行", command=lambda: self.delete_row(iid))
            menu.tk_popup(event.x_root, event.y_root)
        else:
            # 空白处右键：全局菜单
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="刷新", command=self.reload_data)
            menu.tk_popup(event.x_root, event.y_root)

    def copy_code(self, iid):
        val = self.tree.set(iid, "Code")
        self.clipboard_clear()
        self.clipboard_append(val)

    def show_details(self, iid):
        vals = self.tree.item(iid, "values")
        tk.messagebox.showinfo("详情", "\n".join(f"{c}: {v}" for c, v in zip(self.tree["columns"], vals)))

    def delete_row(self, iid):
        self.tree.delete(iid)

    def sort_by(self, col, descending):
        """列排序（数值列尝试按数字排序）"""
        data = [(self.tree.set(child, col), child) for child in self.tree.get_children("")]
        # 尝试把值转成数字
        try:
            data = [(float(d[0]), d[1]) for d in data]
        except Exception:
            data = [(d[0].lower(), d[1]) for d in data]

        data.sort(reverse=descending)
        # 重建顺序
        for index, (val, iid) in enumerate(data):
            self.tree.move(iid, "", index)
            # 更新交替色
            self.tree.item(iid, tags=("oddrow" if index % 2 == 0 else "evenrow",))
        # 切换下次排序方向
        self.tree.heading(col, command=lambda: self.sort_by(col, not descending))

# -------------------------
# 运行
# -------------------------
if __name__ == "__main__":
    app = App()
    app.mainloop()
