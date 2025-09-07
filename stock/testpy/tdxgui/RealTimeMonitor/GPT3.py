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
ROW_EVEN = "#E9F8F0"
TEXT_COLOR = "#222222"
HIGHLIGHT = "#FFF8C5"

# ------------------------
# 数据生成函数
# ------------------------
def gen_row(i):
    name = f"Item {i}"
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    value = round(random.uniform(1, 1000), 2)
    tag = random.choice(["A", "B", "C"])
    return (name, code, value, tag)

# ------------------------
# 界面初始化
# ------------------------
def init_app():
    global root, tree, search_var, _data_source, _insert_index, _chunk_size, _loading, executor
    root = tk.Tk()
    root.title("CleanTree Modern Fixed")
    root.overrideredirect(True)
    root.geometry("900x560+120+120")
    root.configure(bg=BG)

    # 拖动和最大化数据
    root._drag_data = {"x":0,"y":0}
    root._is_max = False
    root._restore_geom = None

    # 样式
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Treeview",
                    background=ROW_ODD,
                    fieldbackground=ROW_ODD,
                    foreground=TEXT_COLOR,
                    rowheight=28,
                    font=("Segoe UI", 10))
    style.map("Treeview", background=[("selected", ACCENT)])
    style.configure("Custom.TButton",
                    background=TITLE_BG,
                    foreground=TITLE_FG,
                    relief="flat",
                    font=("Segoe UI", 9, "bold"))
    style.configure("Search.TEntry", fieldbackground="#FFFFFF", foreground="#000000")

    create_titlebar()
    create_body()

    root.bind("<Escape>", lambda e: root.destroy())

    _data_source = []
    _insert_index = 0
    _chunk_size = 200
    _loading = False
    executor = ThreadPoolExecutor(max_workers=2)

    reload_data()

# ------------------------
# 标题栏
# ------------------------
def create_titlebar():
    titlebar = tk.Frame(root, bg=TITLE_BG, height=36)
    titlebar.pack(fill="x", side="top")
    lbl = tk.Label(titlebar, text="  CleanTree Modern Fixed", bg=TITLE_BG, fg=TITLE_FG,
                   font=("Segoe UI", 10, "bold"))
    lbl.pack(side="left", padx=6)
    btn_frame = tk.Frame(titlebar, bg=TITLE_BG)
    btn_frame.pack(side="right", padx=6)
    min_btn = tk.Button(btn_frame, text="—", bg=TITLE_BG, fg=TITLE_FG,
                        bd=0, relief="flat", command=root.iconify,
                        font=("Segoe UI", 12))
    min_btn.pack(side="right", padx=4)
    close_btn = tk.Button(btn_frame, text="✕", bg=TITLE_BG, fg=TITLE_FG,
                          bd=0, relief="flat", command=root.destroy,
                          font=("Segoe UI", 11))
    close_btn.pack(side="right", padx=4)

    for btn in (min_btn, close_btn):
        btn.bind("<Enter>", lambda e,b=btn: b.config(bg="#3A3F4B"))
        btn.bind("<Leave>", lambda e,b=btn: b.config(bg=TITLE_BG))

    for w in (titlebar, lbl):
        w.bind("<ButtonPress-1>", start_move)
        w.bind("<ButtonRelease-1>", stop_move)
        w.bind("<B1-Motion>", on_move)
    titlebar.bind("<Double-Button-1>", toggle_max_restore)

def start_move(event):
    root._drag_data["x"] = event.x
    root._drag_data["y"] = event.y

def stop_move(event):
    root._drag_data = {"x":0,"y":0}

def on_move(event):
    x = event.x_root - root._drag_data["x"]
    y = event.y_root - root._drag_data["y"]
    root.geometry(f"+{x}+{y}")

def toggle_max_restore(event=None):
    if not root._is_max:
        root._restore_geom = root.geometry()
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        root.geometry(f"{screen_w}x{screen_h}+0+0")
        root._is_max = True
    else:
        if root._restore_geom:
            root.geometry(root._restore_geom)
        root._is_max = False

# ------------------------
# 主体界面
# ------------------------
def create_body():
    global tree, search_var
    container = tk.Frame(root, bg=BG)
    container.pack(fill="both", expand=True, padx=12, pady=12)

    # 工具栏
    toolbar = tk.Frame(container, bg=BG)
    toolbar.pack(fill="x", pady=(0,8))
    tk.Label(toolbar, text="Search:", bg=BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).pack(side="left")
    search_var = tk.StringVar()
    search_entry = ttk.Entry(toolbar, textvariable=search_var, width=30, style="Search.TEntry")
    search_entry.pack(side="left", padx=(8,6))
    search_entry.bind("<KeyRelease>", lambda e: highlight_search())
    search_btn = ttk.Button(toolbar, text="搜索", style="Custom.TButton", command=highlight_search)
    search_btn.pack(side="left", padx=(4,6))
    clear_btn = ttk.Button(toolbar, text="重置", style="Custom.TButton", command=reset_filter)
    clear_btn.pack(side="left", padx=(4,6))
    refresh_btn = ttk.Button(toolbar, text="刷新数据", style="Custom.TButton", command=reload_data)
    refresh_btn.pack(side="right", padx=(4,6))

    # TreeView
    tree_frame = tk.Frame(container, bg=BG)
    tree_frame.pack(fill="both", expand=True)
    cols = ("Name","Code","Value","Tag")
    tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
    for c in cols:
        tree.heading(c, text=c, command=lambda _c=c: sort_by(_c, False))
        tree.column(c, anchor="w", minwidth=80, width=160)
    tree.tag_configure("oddrow", background=ROW_ODD)
    tree.tag_configure("evenrow", background=ROW_EVEN)
    tree.grid(row=0,column=0,sticky="nsew")
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.grid(row=0,column=1,sticky="ns")
    hsb.grid(row=1,column=0,sticky="ew")
    tree_frame.rowconfigure(0,weight=1)
    tree_frame.columnconfigure(0,weight=1)
    tree.bind("<Double-1>", on_double_click)
    tree.bind("<Button-3>", on_right_click)

# ------------------------
# 数据加载
# ------------------------
def reload_data():
    global _data_source, _insert_index, _chunk_size, _loading
    for i in tree.get_children():
        tree.delete(i)
    _insert_index = 0
    N = 4000
    _data_source = [gen_row(i) for i in range(1,N+1)]
    _loading = True
    root.after(10, chunk_insert)

def chunk_insert():
    global _insert_index, _chunk_size, _data_source, _loading
    start = _insert_index
    end = min(start+_chunk_size, len(_data_source))
    for idx in range(start,end):
        row = _data_source[idx]
        tag = "oddrow" if idx%2==0 else "evenrow"
        tree.insert("", "end", values=(row[0],row[1],f"{row[2]:.2f}",row[3]), tags=(tag,))
    _insert_index = end
    if _insert_index < len(_data_source):
        root.after(8, chunk_insert)
    else:
        _loading = False
        autosize_columns()

def autosize_columns():
    for col in tree["columns"]:
        max_w = 60
        hdr = col
        w = tkfont.Font(font=("Segoe UI",10,"bold")).measure(hdr)+18
        max_w = max(max_w,w)
        children = tree.get_children()
        sample = children[:200] if len(children)>200 else children
        f = tkfont.Font(font=("Segoe UI",10))
        for iid in sample:
            val = str(tree.set(iid,col))
            w = f.measure(val)+18
            if w>max_w: max_w=w
        tree.column(col,width=min(max_w,600))

# ------------------------
# 搜索高亮
# ------------------------
def highlight_search(event=None):
    q = search_var.get().strip().lower()
    for iid in tree.get_children():
        vals = tree.item(iid,"values")
        if any(q in str(v).lower() for v in vals) and q!="":
            tree.item(iid, tags=("highlight",))
        else:
            tag = "oddrow" if int(iid[1:],16)%2==0 else "evenrow"
            tree.item(iid, tags=(tag,))
    tree.tag_configure("highlight", background=HIGHLIGHT)

def reset_filter():
    search_var.set("")
    for iid in tree.get_children():
        tag = "oddrow" if int(iid[1:],16)%2==0 else "evenrow"
        tree.item(iid, tags=(tag,))

# ------------------------
# 双击/右键
# ------------------------
def on_double_click(event):
    item = tree.selection()
    if item:
        vals = tree.item(item[0],"values")
        messagebox.showinfo("详情", f"Name:{vals[0]}\nCode:{vals[1]}\nValue:{vals[2]}\nTag:{vals[3]}")

def on_right_click(event):
    iid = tree.identify_row(event.y)
    if iid:
        tree.selection_set(iid)
        menu = tk.Menu(root, tearoff=0)
        menu.add_command(label="复制", command=lambda: copy_item(iid))
        menu.add_command(label="删除", command=lambda: tree.delete(iid))
        menu.tk_popup(event.x_root,event.y_root)

def copy_item(iid):
    vals = tree.item(iid,"values")
    s = "\t".join(str(v) for v in vals)
    root.clipboard_clear()
    root.clipboard_append(s)
    messagebox.showinfo("已复制", s)

# ------------------------
# 列排序
# ------------------------
def sort_by(col, descending):
    data = [(tree.set(k,col),k) for k in tree.get_children('')]
    try:
        data.sort(key=lambda t: float(t[0]), reverse=descending)
    except ValueError:
        data.sort(reverse=descending)
    for idx,(val,k) in enumerate(data):
        tree.move(k,'',idx)
    tree.heading(col, command=lambda: sort_by(col, not descending))

# ------------------------
# 启动
# ------------------------
if __name__=="__main__":
    init_app()
    root.mainloop()
