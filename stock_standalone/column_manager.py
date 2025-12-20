# -*- coding:utf-8 -*-
import tkinter as tk
from tkinter import ttk
from stock_logic_utils import  toast_message
from JohnsonUtil import LoggerFactory

# 获取或创建日志记录器
logger = LoggerFactory.getLogger("instock_TK.KLineMonitor")
class ColumnSetManager(tk.Toplevel):
    def __init__(self, master, all_columns, config, on_apply_callback, default_cols, auto_apply_on_init=False,logger=logger):
        super().__init__(master)
        self.master = master
        self.title("列组合管理器")
        # ---------- 基础尺寸 ----------
        self.width = 800
        self.height = 500
        self.geometry(f"{self.width}x{self.height}")

        # ---------- 参数 ----------
        self.all_columns = list(all_columns)
        self.config = config if isinstance(config, dict) else {}
        self.on_apply_callback = on_apply_callback
        self.default_cols = list(default_cols)
        self.auto_apply_on_init = auto_apply_on_init

        # ---------- 状态 ----------
        self.current_set = list(self.config.get("current", self.default_cols.copy()))
        self.saved_sets = list(self.config.get("sets", []))
        self._chk_vars = {}
        self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}
        self._resize_job = None

        # ---------- 构建 UI ----------
        self._build_ui()

        # 延迟首次布局
        self.after(80, self.update_grid)

        # ---------- 自动应用列组合 ----------
        if self.auto_apply_on_init:
            try:
                self.withdraw()  # 先隐藏
                self.set_current_set()  # 调用回调更新列
                # 可选择应用后显示或保持隐藏
                # self.deiconify()
            except Exception as e:
                traceback.print_exc()
                logger.info(f"⚠️ 自动应用列组合失败：{e}")

    def _build_ui(self):
        # ---------- 高 DPI 初始化 ----------
        # try:
        #     from ctypes import windll
        #     windll.shcore.SetProcessDpiAwareness(1)  # Windows 高 DPI 感知
        # except:
        #     pass
        # dpi_scale = self.winfo_fpixels('1i') / 72  # 获取 DPI 缩放比例
        dpi_scale = self.master.scale_factor
        # dpi_scale = get_windows_dpi_scale_factor()
        base_width, base_height = 800, 500
        self.width = int(base_width * dpi_scale)
        self.height = int(base_height * dpi_scale)
        self.geometry(f"{self.width}x{self.height}")

        # ---------- 主容器 ----------
        self.main = ttk.Frame(self)
        self.main.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(self.main)
        top.pack(fill=tk.BOTH, expand=True, padx=6, pady=1)

        # 使用 grid 管理左右比例，左 3/4，右 1/4
        top.grid_columnconfigure(0, weight=3)
        top.grid_columnconfigure(1, weight=1)
        top.grid_rowconfigure(0, weight=1)

        # 左侧容器
        left = ttk.Frame(top)
        left.grid(row=0, column=0, sticky="nsew")

        # 右侧容器
        right = ttk.Frame(top)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)

        # ---------- 搜索栏 ----------
        search_frame = ttk.Frame(left)
        search_frame.pack(fill=tk.X, pady=(0,6))
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.search_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6,0))
        entry.bind("<KeyRelease>", lambda e: self._debounced_update())

        # ---------- 列选择区（Canvas + Scrollable Frame） ----------
        grid_container = ttk.Frame(left)
        grid_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(grid_container)
        self.vscroll = ttk.Scrollbar(grid_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.inner_frame = ttk.Frame(self.canvas)
        self.inner_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0,0), window=self.inner_frame, anchor="nw")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮
        self.canvas.bind("<Enter>", lambda e: self._bind_mousewheel(True))
        self.canvas.bind("<Leave>", lambda e: self._bind_mousewheel(False))

        # ---------- 当前组合标签 ----------
        current_lf = ttk.LabelFrame(left, text="当前组合")
        current_lf.pack(fill=tk.X, pady=(6,0))
        self.current_frame = tk.Frame(current_lf)
        self.current_frame.pack(fill=tk.X, padx=4, pady=6)
        self.current_frame.bind("<Configure>", lambda e: self._debounced_refresh_tags())

        # ---------- 右侧：已保存组合列表 ----------
        ttk.Label(right, text="已保存组合").pack(anchor="w", padx=6, pady=(6,0))
        self.sets_listbox = tk.Listbox(right, exportselection=False)
        self.sets_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.sets_listbox.bind("<<ListboxSelect>>", self.on_select_saved_set)
        self.sets_listbox.bind("<Double-1>", lambda e: self.load_selected_set())

        sets_btns = ttk.Frame(right)
        sets_btns.pack(fill=tk.X, padx=6, pady=(0,6))
        ttk.Button(sets_btns, text="加载", command=self.load_selected_set).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(sets_btns, text="删除", command=self.delete_selected_set).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        self.lbl_current_set = ttk.Label(right, text="当前选中: (无)")
        self.lbl_current_set.pack(anchor="w", padx=6, pady=(0,4))

        # ---------- 底部按钮 ----------
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(bottom, text="保存组合", command=self.save_current_set).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(bottom, text="应用组合", command=self.apply_current_set).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=6)
        ttk.Button(bottom, text="恢复默认", command=self.restore_default).pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ---------- 快捷键 ----------
        self.bind("<Alt-c>", lambda e: self.open_column_manager_editor())
        self.bind("<Escape>", lambda e: self.open_column_manager_editor())

        # ---------- 填充保存组合列表 ----------
        self.refresh_saved_sets()

        # ---------- 自动应用当前列组合 ----------
        if self.auto_apply_on_init:
            try:
                self.set_current_set()
            except Exception as e:
                traceback.print_exc()
                logger.info(f"⚠️ 自动应用列组合失败：{e}")



  


    def open_column_manager_editor(self):
        """切换显示/隐藏"""
        if self.state() == "withdrawn":
            # 已隐藏 → 显示
            self.deiconify()
            self.lift()
            self.focus_set()
        else:
            # 已显示 → 隐藏
            self.withdraw()


    # ---------------------------
    # 鼠标滚轮支持（只在 canvas 区生效）
    # ---------------------------
    def _bind_mousewheel(self, bind: bool):
        # Windows: <MouseWheel> with event.delta; Linux: Button-4/5
        if bind:
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
            self.canvas.bind_all("<Button-4>", self._on_mousewheel)
            self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        else:
            try:
                self.canvas.unbind_all("<MouseWheel>")
                self.canvas.unbind_all("<Button-4>")
                self.canvas.unbind_all("<Button-5>")
            except Exception:
                pass

    def _on_mousewheel(self, event):
        # cross-platform wheel handling
        if event.num == 4:  # Linux scroll up
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:  # Linux scroll down
            self.canvas.yview_scroll(1, "units")
        else:
            # Windows / Mac
            delta = int(-1*(event.delta/120))
            self.canvas.yview_scroll(delta, "units")

    def _debounced_update(self):
        self.update_grid()

    def _debounced_refresh_tags(self):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(180, self.refresh_current_tags)

    def default_filter(self,c):
        if c in self.current_set:
            return True
        # keywords = ["perc","percent","trade","volume","boll","macd","ma"]
        keywords = ["perc","status","obs","hold","bull","has","lastdu","red","ma"]
        return any(k in c.lower() for k in keywords)

    # ---------------------------
    # 列选择区更新（Checkbuttons 自动排列）
    # ---------------------------
    def update_grid(self):
        # 清空旧的 checkbuttons
        for w in self.inner_frame.winfo_children():
            w.destroy()
        self._chk_vars.clear()

        # filter
        search = (self.search_var.get() or "").lower()
        # logger.info(f'search : {search}')
        if search == "":
            filtered = [c for c in self.all_columns if self.default_filter(c)]
        elif search == "no" or search == "other":
            filtered = [c for c in self.all_columns if not self.default_filter(c)]
        else:
            filtered = [c for c in self.all_columns if search in c.lower()]


        filtered = filtered[:200]  # 可以扩展，但前面限制为 50/200

        # 计算每行列数（使用 canvas 宽度 fallback）
        self.update_idletasks()
        total_width = self.canvas.winfo_width() if self.canvas.winfo_width() > 600 else self.width
        col_w = 100
        cols_per_row = max(3, total_width // col_w - 2)

        # 计算高度（最多显示 max_rows 行）
        rows_needed = (len(filtered) + cols_per_row - 1) // cols_per_row
        max_rows = 4
        row_h = 30
        canvas_h = min(rows_needed, max_rows) * row_h
        self.canvas.config(height=canvas_h)
        # logger.info(f'max_rows:{max_rows} rows_needed:{rows_needed} canvas_h:{canvas_h}')
        for i, col in enumerate(filtered):
            var = tk.BooleanVar(value=(col in self.current_set))
            self._chk_vars[col] = var
            chk = ttk.Checkbutton(self.inner_frame, text=col, variable=var,
                                  command=lambda c=col, v=var: self._on_check_toggle(c, v.get()))
            chk.grid(row=i // cols_per_row, column=i % cols_per_row, sticky="w", padx=4, pady=3)

        # 刷新当前组合标签显示
        # logger.info(f'update_grid')
        self.refresh_current_tags()

    def _on_check_toggle(self, col, state):
        if state:
            if col not in self.current_set:
                self.current_set.append(col)
        else:
            if col in self.current_set:
                self.current_set.remove(col)
        # logger.info(f'_on_check_toggle')
        self.refresh_current_tags()

    # ---------------------------
    # 当前组合标签显示 + 拖拽重排
    # ---------------------------
    def refresh_current_tags(self):
        # 清空
        for w in self.current_frame.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        # 可能窗口刚弹出，宽度还没算好 -> fallback
        max_w = self.current_frame.winfo_width()
        if not max_w or max_w < 20:
            max_w = self.width - 40

        # 计算每个标签位置并 place
        y = 0
        x = 4
        row_h = 28
        padding = 6

        # 用于存放标签和位置信息
        self._tag_widgets = []

        for idx, col in enumerate(self.current_set):
            lbl = tk.Label(self.current_frame, text=col, bd=1, relief="solid", padx=6, pady=2, bg="#e8e8e8")
            lbl.update_idletasks()
            try:
                w_req = lbl.winfo_reqwidth()
            except tk.TclError:
                w_req = 80
            if x + w_req > max_w - 10:
                # 换行
                y += row_h
                x = 4

            # place at (x,y)
            lbl.place(x=x, y=y)
            # 保存 widget 及位置数据（仅用于拖拽计算）
            self._tag_widgets.append({"widget": lbl, "x": x, "y": y, "w": w_req, "idx": idx})
            # 绑定拖拽事件（闭包捕获 idx）
            lbl.bind("<Button-1>", lambda e, i=idx: self._start_drag(e, i))
            lbl.bind("<B1-Motion>", self._on_drag)
            lbl.bind("<ButtonRelease-1>", self._end_drag)
            x += w_req + padding

        # 更新 frame 高度以容纳所有行
        total_height = y + row_h + 4
        try:
            self.current_frame.config(height=total_height)
            # logger.info(f'total_height:{total_height}')

        except Exception:
            pass

    def _start_drag(self, event, idx):
        """开始拖拽"""
        widget = event.widget
        widget.lift()
        self._drag_data = {
            "widget": widget,
            "start_x": event.x_root,
            "start_y": event.y_root,
            "idx": idx,
        }

        # --- 安全创建提示线 ---
        try:
            if not hasattr(self, "_insert_line") or not self._insert_line.winfo_exists() \
                    or self._insert_line.master != self.current_frame:
                self._insert_line = tk.Frame(self.current_frame, bg="#0078d7", width=2, height=26)
        except Exception:
            self._insert_line = tk.Frame(self.current_frame, bg="#0078d7", width=2, height=26)

        try:
            self._insert_line.place_forget()
        except Exception:
            pass

        logger.info(f"_start_drag {idx}")


    def _on_drag(self, event):
        """拖拽中"""
        lbl = self._drag_data.get("widget")
        if not lbl:
            return

        # --- 移动标签跟随光标 ---
        frame_x = self.current_frame.winfo_rootx()
        frame_y = self.current_frame.winfo_rooty()
        new_x = event.x_root - frame_x - 10
        new_y = event.y_root - frame_y - 8

        try:
            lbl.place(x=new_x, y=new_y)
        except Exception:
            return

        # --- 计算插入位置 ---
        drop_cx = event.x_root - frame_x
        drop_cy = event.y_root - frame_y
        centers = []

        for info in getattr(self, "_tag_widgets", []):
            w = info["widget"]
            if not w.winfo_exists() or w is lbl:
                continue
            cx = w.winfo_x() + info["w"] / 2
            cy = w.winfo_y() + 14  # 行中心
            centers.append((cx, cy, w, info["idx"]))

        if not centers:
            if hasattr(self, "_insert_line") and self._insert_line.winfo_exists():
                self._insert_line.place_forget()
            return

        # --- 找最近标签 ---
        centers.sort(key=lambda x: ((x[0] - drop_cx) ** 2 + (x[1] - drop_cy) ** 2))
        nearest_cx, nearest_cy, nearest_widget, nearest_idx = centers[0]

        # 判断插入线位置（在前或在后）
        if drop_cx < nearest_cx:
            x_line = nearest_widget.winfo_x() - 2
            y_line = nearest_widget.winfo_y()
        else:
            x_line = nearest_widget.winfo_x() + nearest_widget.winfo_width() + 2
            y_line = nearest_widget.winfo_y()

        # --- 显示插入提示线 ---
        try:
            if hasattr(self, "_insert_line") and self._insert_line.winfo_exists():
                self._insert_line.place(x=x_line, y=y_line)
                self._insert_line.lift()
        except Exception:
            pass


    def _end_drag(self, event):
        """拖拽结束"""
        lbl = self._drag_data.get("widget")
        orig_idx = self._drag_data.get("idx")

        # 隐藏插入线
        try:
            if hasattr(self, "_insert_line") and self._insert_line.winfo_exists():
                self._insert_line.place_forget()
        except Exception:
            pass

        if not lbl or orig_idx is None:
            self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}
            return

        # --- 计算拖放位置 ---
        frame_x = self.current_frame.winfo_rootx()
        frame_y = self.current_frame.winfo_rooty()
        drop_cx = event.x_root - frame_x
        drop_cy = event.y_root - frame_y

        centers = []
        for info in getattr(self, "_tag_widgets", []):
            w = info["widget"]
            if not w.winfo_exists() or w is lbl:
                continue
            cx = w.winfo_x() + info["w"] / 2
            cy = w.winfo_y() + 14
            centers.append((cx, cy, info["idx"]))

        if not centers:
            new_idx = 0
        else:
            centers.sort(key=lambda x: ((x[0] - drop_cx) ** 2 + (x[1] - drop_cy) ** 2))
            nearest_cx, nearest_cy, nearest_idx = centers[0]

            if drop_cx < nearest_cx:
                new_idx = nearest_idx
            else:
                new_idx = nearest_idx + 1

            new_idx = max(0, min(len(self.current_set), new_idx))

        # --- 调整顺序 ---
        if new_idx != orig_idx:
            try:
                item = self.current_set.pop(orig_idx)
                if new_idx > orig_idx:
                    new_idx -= 1  # 因 pop 导致右移
                self.current_set.insert(new_idx, item)
            except Exception as e:
                logger.info(f"Reorder error:{e}")

        # logger.info(f"drag: {orig_idx} → {new_idx}")

        # --- 清理 & 刷新 ---
        self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}
        self.after(100, self.refresh_current_tags)


    # ---------------------------
    # 已保存组合管理
    # ---------------------------
    def refresh_saved_sets(self):
        self.sets_listbox.delete(0, tk.END)
        for s in self.saved_sets:
            name = s.get("name", "<noname>")
            self.sets_listbox.insert(tk.END, name)

    def get_centered_window_position(self, parent, win_width, win_height, margin=10):
        # 获取鼠标位置
        mx = parent.winfo_pointerx()
        my = parent.winfo_pointery()

        # 屏幕尺寸
        screen_width = parent.winfo_screenwidth()
        screen_height = parent.winfo_screenheight()

        # 默认右边放置
        x = mx + margin
        y = my - win_height // 2  # 垂直居中鼠标位置

        # 如果右边放不下，改到左边
        if x + win_width > screen_width:
            x = mx - win_width - margin

        # 防止y超出屏幕
        if y + win_height > screen_height:
            y = screen_height - win_height - margin
        if y < 0:
            y = margin

        return x, y

    def askstring_at_parent(self, parent, title, prompt, initialvalue=""):

        # 创建临时窗口
        dlg = tk.Toplevel(parent)
        dlg.transient(parent)
        dlg.title(title)
        dlg.resizable(True, True)  # ✅ 可自由拉伸

        # --- 智能计算初始大小 ---
        base_width, base_height = 300, 120
        char_width = 10
        text_len = max(len(prompt), len(initialvalue))
        extra_width = min(text_len * char_width, 600)
        win_width = max(base_width, extra_width)
        win_height = base_height + (prompt.count("\n") * 15)  # 多行时稍高

        # --- 居中定位 ---
        x, y = self.get_centered_window_position(parent, win_width, win_height)
        logger.info(f"askstring_at_parent : {int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")
        dlg.geometry(f"{int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")

        result = {"value": None}

        # --- 提示文字（自动换行） ---
        lbl = tk.Label(dlg, text=prompt, wraplength=win_width - 40, justify="left", anchor="w")
        lbl.pack(pady=5, padx=5, fill="x")

        # --- 输入框 ---
        entry = tk.Entry(dlg)
        entry.pack(pady=5, padx=5, fill="x", expand=True)
        entry.insert(0, initialvalue)
        entry.focus_set()

        # --- 按钮 ---
        def on_ok():
            result["value"] = entry.get()
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        frame_btn = tk.Frame(dlg)
        frame_btn.pack(pady=5)
        tk.Button(frame_btn, text="确定", width=10, command=on_ok).pack(side="left", padx=5)
        tk.Button(frame_btn, text="取消", width=10, command=on_cancel).pack(side="left", padx=5)

        # --- ESC 键关闭 ---
        dlg.bind("<Escape>", lambda e: on_cancel())
        dlg.bind("<Return>",lambda e: on_ok())       # 回车确认

        dlg.grab_set()
        parent.wait_window(dlg)
        return result["value"]


    def save_current_set(self):
        if not self.current_set:
            toast_message(self, "当前组合为空")
            return
        # 取当前组合名称（或默认空字符串）
        current_name = getattr(self, "current_set_name", "") or ""
        name = self.askstring_at_parent(self.main,"保存组合", "请输入组合名称:",initialvalue=current_name)

        if not name:
            return
        # 覆盖同名
        for s in self.saved_sets:
            if s.get("name") == name:
                s["cols"] = list(self.current_set)
                toast_message(self, f"组合 {name} 已更新")
                self.refresh_saved_sets()
                return
        self.saved_sets.append({"name": name, "cols": list(self.current_set)})
        self.refresh_saved_sets()
        try:
            # save_display_config 是外部函数（如果定义则调用）
            self.config["current"] = list(self.current_set)
            self.config["sets"] = list(self.saved_sets)
            save_display_config(config_file=CONFIG_FILE,config=self.config)
        except Exception:
            pass
        # 回调主视图更新列
        toast_message(self, f"组合 {name} 已保存")

    def on_select_saved_set(self, event):
        sel = self.sets_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        data = self.saved_sets[idx]
        self.current_set_name = data.get("name", "")

        # 可选：在界面上显示当前选择的组合名
        if hasattr(self, "lbl_current_set"):
            self.lbl_current_set.config(text=f"当前选中: {self.current_set_name}")
        else:
            logger.info(f"选中组合: {self.current_set_name}")


    def load_selected_set(self):
        sel = self.sets_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        data = self.saved_sets[idx]
        self.current_set = list(data.get("cols", []))

        # 保存当前组合名称（新增）
        self.current_set_name = data.get("name", "")

        # sync checkboxes (if visible)
        for col, var in self._chk_vars.items():
            var.set(col in self.current_set)
        self.refresh_current_tags()
        # also update grid so checked box matches
        self.update_grid()

    def delete_selected_set(self):
        sel = self.sets_listbox.curselection()
        if not sel:
            toast_message(self, "请选择要删除的组合")
            return
        idx = sel[0]
        name = self.saved_sets[idx].get("name", "")
        # 执行删除
        self.saved_sets.pop(idx)
        self.refresh_saved_sets()
        toast_message(self, f"组合 {name} 已删除")

    # ---------------------------
    # 应用 / 恢复默认
    # ---------------------------

    def set_current_set(self):
        if not self.current_set:
            toast_message(self, "当前组合为空")
            return
        try:
            if callable(self.on_apply_callback):
                self.on_apply_callback(list(self.current_set))
        except Exception:
            pass

    def apply_current_set(self):
        if not self.current_set:
            toast_message(self, "当前组合为空")
            return
        # 写回 config（如果调用方提供 save_display_config，会被调用）
        self.config["current"] = list(self.current_set)
        self.config["sets"] = list(self.saved_sets)
        try:
            # save_display_config 是外部函数（如果定义则调用）
            save_display_config(config_file=CONFIG_FILE,config=self.config)
        except Exception:
            pass
        # 回调主视图更新列
        try:
            if callable(self.on_apply_callback):
                self.on_apply_callback(list(self.current_set))
        except Exception:
            pass
        toast_message(self, "组合已应用")
        # self.destroy()
        self.open_column_manager_editor()

    def restore_default(self):
        self.current_set = list(self.default_cols)
        # logger.info(f'restore_default self.default_cols : {self.default_cols}')
        # sync checkboxes
        for col, var in self._chk_vars.items():
            var.set(col in self.current_set)
        self.refresh_current_tags()
        toast_message(self, "已恢复默认组合")