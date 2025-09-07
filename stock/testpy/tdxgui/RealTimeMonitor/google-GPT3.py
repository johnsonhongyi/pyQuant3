import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
import random
import string
import threading
from concurrent.futures import ThreadPoolExecutor
import time

# ------------------------
# 全局常量和样式配置
# ------------------------
BG = "#F6F8FA"
TITLE_BG = "#2B2F3A"
TITLE_FG = "#FFFFFF"
ACCENT = "#4C9F70"
ROW_ODD = "#FFFFFF"
ROW_EVEN = "#E9F8F0"
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
# 单功能函数
# ------------------------
def run_app():
    # ------------------------
    # UI 逻辑
    # ------------------------
    def create_titlebar(root, drag_data, toggle_max_restore):
        titlebar = tk.Frame(root, bg=TITLE_BG, height=36)
        titlebar.pack(fill="x", side="top")
        lbl = tk.Label(titlebar, text="  CleanTree Modern Fixed", bg=TITLE_BG, fg=TITLE_FG,
                       font=("Segoe UI", 10, "bold"))
        lbl.pack(side="left", padx=6)

        def start_move(event):
            drag_data["x"] = event.x
            drag_data["y"] = event.y

        def stop_move(event):
            drag_data["x"] = 0
            drag_data["y"] = 0

        def on_move(event):
            x = event.x_root - drag_data["x"]
            y = event.y_root - drag_data["y"]
            root.geometry(f"+{x}+{y}")

        btn_frame = tk.Frame(titlebar, bg=TITLE_BG)
        btn_frame.pack(side="right", padx=6)
        min_btn = tk.Button(btn_frame, text="—", bg=TITLE_BG, fg=TITLE_FG, bd=0, relief="flat",
                            command=root.iconify, font=("Segoe UI", 12))
        min_btn.pack(side="right", padx=4)
        close_btn = tk.Button(btn_frame, text="✕", bg=TITLE_BG, fg=TITLE_FG, bd=0, relief="flat",
                              command=root.destroy, font=("Segoe UI", 11))
        close_btn.pack(side="right", padx=4)

        for btn in (min_btn, close_btn):
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=HOVER_TITLE_BTN if b != close_btn else HOVER_TITLE_CLOSE))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=TITLE_BG))

        for w in (titlebar, lbl):
            w.bind("<ButtonPress-1>", start_move)
            w.bind("<ButtonRelease-1>", stop_move)
            w.bind("<B1-Motion>", on_move)
        titlebar.bind("<Double-Button-1>", toggle_max_restore)

    def create_body(root, tree, search_var, highlight_search, reset_filter, reload_data, sort_by):
        container = tk.Frame(root, bg=BG)
        container.pack(fill="both", expand=True, padx=12, pady=(12, 12))

        # 工具栏
        toolbar = tk.Frame(container, bg=BG)
        toolbar.pack(fill="x", pady=(0, 8))
        tk.Label(toolbar, text="Search:", bg=BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).pack(side="left")
        search_entry = ttk.Entry(toolbar, textvariable=search_var, width=30, style="Search.TEntry")
        search_entry.pack(side="left", padx=(8, 6))
        search_entry.bind("<KeyRelease>", lambda e: highlight_search())
        
        search_btn = ttk.Button(toolbar, text="搜索", style="Custom.TButton", command=highlight_search)
        search_btn.pack(side="left", padx=(4, 6))
        clear_btn = ttk.Button(toolbar, text="重置", style="Custom.TButton", command=reset_filter)
        clear_btn.pack(side="left", padx=(4, 6))
        refresh_btn = ttk.Button(toolbar, text="刷新数据", style="Custom.TButton", command=reload_data)
        refresh_btn.pack(side="right", padx=(4, 6))

        for btn in (search_btn, clear_btn, refresh_btn):
            btn.bind("<Enter>", lambda e, b=btn: b.configure(style="Hover.TButton"))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(style="Custom.TButton"))

        # TreeView
        tree_frame = tk.Frame(container, bg=BG)
        tree_frame.pack(fill="both", expand=True)
        cols = ("Name", "Code", "Value", "Tag")
        tree_inst = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            tree_inst.heading(c, text=c, command=lambda _c=c: sort_by(_c, False))
            tree_inst.column(c, anchor="w", minwidth=80)
        
        tree_inst.tag_configure("oddrow", background=ROW_ODD)
        tree_inst.tag_configure("evenrow", background=ROW_EVEN)
        
        tree_inst.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree_inst.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree_inst.xview)
        tree_inst.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        tree["inst"] = tree_inst # 存储在字典中以便在其他函数中访问

        # 双击 & 右键
        tree_inst.bind("<Double-1>", on_double_click)
        tree_inst.bind("<Button-3>", on_right_click)

    # ------------------------
    # 数据加载和 Treeview 操作
    # ------------------------
    _data_source = []
    _insert_index = 0
    _chunk_size = 200
    _loading = False
    executor = ThreadPoolExecutor(max_workers=2)

    def reload_data(root, tree):
        nonlocal _insert_index, _loading
        if _loading: return
        for i in tree["inst"].get_children():
            tree["inst"].delete(i)
        _insert_index = 0
        N = 4000
        executor.submit(_generate_data_async, N, root, tree)
        _loading = True

    def _generate_data_async(N, root, tree):
        nonlocal _data_source
        _data_source = [gen_row(i) for i in range(1, N + 1)]
        root.after(10, lambda: _chunk_insert(root, tree))

    def _chunk_insert(root, tree):
        nonlocal _insert_index, _loading
        start = _insert_index
        end = min(start + _chunk_size, len(_data_source))
        for idx in range(start, end):
            row = _data_source[idx]
            tag = "oddrow" if idx % 2 == 0 else "evenrow"
            tree["inst"].insert("", "end", values=(row[0], row[1], f"{row[2]:.2f}", row[3]), tags=(tag,))
        _insert_index = end
        if _insert_index < len(_data_source):
            root.after(8, lambda: _chunk_insert(root, tree))
        else:
            _loading = False
            autosize_columns(root, tree)

    def autosize_columns(root, tree):
        root.after(50, lambda: _perform_autosize(tree))

    def _perform_autosize(tree):
        if not tree["inst"].get_children(): return
        cols = tree["inst"]["columns"]
        font = tkfont.nametofont("Treeview")
        for col_name in cols:
            max_width = font.measure(col_name) + 20
            for item in tree["inst"].get_children():
                try:
                    text = str(tree["inst"].item(item, "values")[cols.index(col_name)])
                    width = font.measure(text)
                    if width > max_width: max_width = width
                except IndexError: pass
            tree["inst"].column(col_name, width=max_width + 20)

    def on_double_click(event):
        tree_inst = tree["inst"]
        item_id = tree_inst.identify_row(event.y)
        if item_id:
            item_values = tree_inst.item(item_id, "values")
            messagebox.showinfo("双击", f"双击了项: {item_values}")

    def on_right_click(event):
        tree_inst = tree["inst"]
        item_id = tree_inst.identify_row(event.y)
        if item_id:
            tree_inst.selection_set(item_id)
            menu = tk.Menu(root, tearoff=0)
            menu.add_command(label="详情", command=lambda: show_details(item_id))
            menu.add_command(label="复制", command=lambda: copy_item(item_id))
            menu.tk_popup(event.x_root, event.y_root)

    def show_details(item_id):
        tree_inst = tree["inst"]
        item_values = tree_inst.item(item_id, "values")
        messagebox.showinfo("详情", f"选中项的详情: {item_values}")

    def copy_item(item_id):
        tree_inst = tree["inst"]
        item_values = tree_inst.item(item_id, "values")
        root.clipboard_clear()
        root.clipboard_append(", ".join(map(str, item_values)))
        messagebox.showinfo("复制", "已复制到剪贴板")

    def highlight_search(search_var, tree):
        query = search_var.get().lower()
        reset_filter(search_var, tree)
        if not query: return
        tree_inst = tree["inst"]
        for item in tree_inst.get_children():
            values = tree_inst.item(item, "values")
            if any(query in str(v).lower() for v in values):
                current_tags = tree_inst.item(item, "tags")
                tree_inst.item(item, tags=current_tags + ("highlight",))
        tree_inst.tag_configure("highlight", background=HIGHLIGHT)

    def reset_filter(search_var, tree):
        search_var.set("")
        tree_inst = tree["inst"]
        for item in tree_inst.get_children():
            current_tags = tree_inst.item(item, "tags")
            new_tags = tuple(t for t in current_tags if t != "highlight")
            tree_inst.item(item, tags=new_tags)
        for idx, item in enumerate(tree_inst.get_children()):
            tag = "oddrow" if idx % 2 == 0 else "evenrow"
            tree_inst.item(item, tags=tag)
            
    def sort_by(col, reverse):
        tree_inst = tree["inst"]
        data = [(tree_inst.set(item, col), item) for item in tree_inst.get_children('')]
        if col == "Value":
            data.sort(key=lambda x: float(x[0]), reverse=reverse)
        else:
            data.sort(reverse=reverse)
        for index, (val, item) in enumerate(data):
            tree_inst.move(item, '', index)
            tag = "oddrow" if index % 2 == 0 else "evenrow"
            tree_inst.item(item, tags=tag)
        tree_inst.heading(col, command=lambda _c=col: sort_by(_c, not reverse))

    # ------------------------
    # 运行主程序
    # ------------------------
    root = tk.Tk()
    root.title("CleanTree Modern Fixed")
    root.overrideredirect(True)
    root.geometry("900x560+120+120")
    root.configure(bg=BG)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Treeview", background=ROW_ODD, fieldbackground=ROW_ODD, foreground=TEXT_COLOR, rowheight=28, font=("Segoe UI", 10))
    style.map("Treeview", background=[("selected", ACCENT)])
    style.configure("Custom.TButton", background=TITLE_BG, foreground=TITLE_FG, relief="flat", font=("Segoe UI", 9, "bold"))
    style.map("Hover.TButton", background=[("active", HOVER_TITLE_BTN)])
    style.configure("Search.TEntry", fieldbackground="#FFFFFF", foreground="#000000")

    drag_data = {"x": 0, "y": 0}
    is_max = False
    restore_geom = None
    
    def toggle_max_restore(event=None):
        nonlocal is_max, restore_geom
        if not is_max:
            restore_geom = root.geometry()
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()
            root.geometry(f"{screen_w}x{screen_h}+0+0")
            is_max = True
        else:
            if restore_geom: root.geometry(restore_geom)
            is_max = False

    tree_ref = {"inst": None} # 使用字典作为可变容器
    search_var = tk.StringVar()
    
    create_titlebar(root, drag_data, toggle_max_restore)
    create_body(root, tree_ref, search_var, 
                lambda: highlight_search(search_var, tree_ref), 
                lambda: reset_filter(search_var, tree_ref), 
                lambda: reload_data(root, tree_ref), sort_by)

    root.bind("<Escape>", lambda e: root.destroy())

    reload_data(root, tree_ref)
    root.mainloop()

# ------------------------
# 运行程序
# ------------------------
if __name__ == "__main__":
    run_app()
