import tkinter as tk
from tkinter import ttk, simpledialog, messagebox


class ColumnSetManager(tk.Toplevel):
    def __init__(self, master, all_columns, on_apply_callback):
        super().__init__(master)
        self.title("列组合管理器")
        self.geometry("800x600")

        self.all_columns = all_columns
        self.on_apply_callback = on_apply_callback
        self.current_set = []  # 当前组合
        self.saved_sets = []   # 历史组合

        self._build_ui()

    def _build_ui(self):
        # 搜索栏
        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.bind("<KeyRelease>", lambda e: self.update_grid())

        # 可选列（按钮网格）
        self.grid_frame = ttk.Frame(self)
        self.grid_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.update_grid()

        # 当前组合
        right_frame = ttk.Frame(self)
        right_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        ttk.Label(right_frame, text="当前组合:").pack(anchor="w")
        self.current_listbox = tk.Listbox(right_frame, selectmode=tk.SINGLE)
        self.current_listbox.pack(fill=tk.BOTH, expand=True)
        self.current_listbox.bind("<Delete>", self.remove_selected_column)

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="↑ 上移", command=lambda: self.move_column(-1)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_frame, text="↓ 下移", command=lambda: self.move_column(1)).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 底部按钮
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, pady=5)
        ttk.Button(bottom, text="保存组合", command=self.save_current_set).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(bottom, text="应用组合", command=self.apply_current_set).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    def update_grid(self):
        # 清空旧的
        for w in self.grid_frame.winfo_children():
            w.destroy()

        search = self.search_var.get().lower()
        filtered = [c for c in self.all_columns if search in c.lower()]

        cols_per_row = 5   # 一行显示几个（可改 3/4/5）
        for i, col in enumerate(filtered):
            btn = ttk.Checkbutton(
                self.grid_frame, text=col,
                command=lambda c=col: self.toggle_column(c)
            )
            if col in self.current_set:
                btn.state(["selected"])
            btn.grid(row=i // cols_per_row, column=i % cols_per_row, sticky="w", padx=3, pady=3)

    def toggle_column(self, col):
        if col in self.current_set:
            self.current_set.remove(col)
        else:
            self.current_set.append(col)
        self.refresh_current_listbox()
        self.update_grid()  # 更新勾选状态

    def refresh_current_listbox(self):
        self.current_listbox.delete(0, tk.END)
        for col in self.current_set:
            self.current_listbox.insert(tk.END, col)

    def remove_selected_column(self, event=None):
        sel = self.current_listbox.curselection()
        if not sel:
            return
        col = self.current_listbox.get(sel[0])
        self.current_set.remove(col)
        self.refresh_current_listbox()
        self.update_grid()

    def move_column(self, direction):
        sel = self.current_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        new_idx = idx + direction
        if 0 <= new_idx < len(self.current_set):
            self.current_set[idx], self.current_set[new_idx] = self.current_set[new_idx], self.current_set[idx]
            self.refresh_current_listbox()
            self.current_listbox.selection_set(new_idx)

    def save_current_set(self):
        if not self.current_set:
            messagebox.showwarning("提示", "当前组合为空")
            return
        name = simpledialog.askstring("保存组合", "请输入组合名称:")
        if not name:
            return
        self.saved_sets.append({"name": name, "cols": list(self.current_set)})
        messagebox.showinfo("保存成功", f"组合 {name} 已保存")

    def apply_current_set(self):
        if not self.current_set:
            messagebox.showwarning("提示", "当前组合为空")
            return
        self.on_apply_callback(self.current_set)
        self.destroy()


# --- 使用示例 ---
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    allcolumns = [
        "name", "trade", "ma5d", "ma10d", "ma20d",
        "perc1d", "perc2d", "perc3d", "macd", "rsi",
        "boll", "upper", "lower", "volume", "turnover",
        "high", "low", "open", "close", "percent"
    ]

    def on_apply(cols):
        print("应用组合:", cols)

    ColumnSetManager(root, allcolumns, on_apply).mainloop()
