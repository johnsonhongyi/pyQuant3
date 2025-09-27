# import tkinter as tk
# from tkinter import ttk, messagebox, simpledialog
# import json, os

# SEARCH_HISTORY_FILE = "search_history.json"

# class QueryHistoryManager:
#     def __init__(self, root):
#         self.root = root
#         self.root.title("Query History Manager")

#         # 加载历史
#         self.history1, self.history2 = self.load_search_history()
#         self.current_history = self.history1  # 默认管理 history1
#         self.current_key = "history1"

#         # --- 输入区 ---
#         frame_input = tk.Frame(root)
#         frame_input.pack(fill="x", padx=5, pady=5)

#         tk.Label(frame_input, text="Query:").pack(side="left")
#         self.entry_query = tk.Entry(frame_input, width=60)
#         self.entry_query.pack(side="left", padx=5)

#         btn_add = tk.Button(frame_input, text="保存", command=self.add_query)
#         btn_add.pack(side="left", padx=5)

#         # 下拉选择管理 history1 / history2
#         self.combo_group = ttk.Combobox(frame_input, values=["history1", "history2"], state="readonly", width=10)
#         self.combo_group.set("history1")
#         self.combo_group.pack(side="left", padx=5)
#         self.combo_group.bind("<<ComboboxSelected>>", self.switch_group)

#         # --- Treeview ---
#         self.tree = ttk.Treeview(root, columns=("query", "star", "note"), show="headings", height=12)
#         self.tree.heading("query", text="Query")
#         self.tree.heading("star", text="⭐")
#         self.tree.heading("note", text="备注")
#         self.tree.column("query", width=400, anchor="w")
#         self.tree.column("star", width=40, anchor="center")
#         self.tree.column("note", width=200, anchor="w")
#         self.tree.pack(fill="both", expand=True, padx=5, pady=5)

#         # 单击星标
#         self.tree.bind("<Button-1>", self.on_click_star)

#         # 双击修改
#         self.tree.bind("<Double-1>", self.on_double_click)

#         # --- 操作按钮 ---
#         frame_btn = tk.Frame(root)
#         frame_btn.pack(fill="x", padx=5, pady=5)

#         tk.Button(frame_btn, text="使用选中Query", command=self.use_query).pack(side="left", padx=5)

#         self.refresh_tree()

#     # ========== 数据存取 ==========
#     def save_search_history(self):
#         """保存到文件"""
#         try:
#             data = {
#                 "history1": self.history1,
#                 "history2": self.history2
#             }
#             with open(SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
#                 json.dump(data, f, ensure_ascii=False, indent=2)
#         except Exception as e:
#             messagebox.showerror("错误", f"保存搜索历史失败: {e}")

#     # def load_search_history(self):
#     #     """从文件加载"""
#     #     if os.path.exists(SEARCH_HISTORY_FILE):
#     #         try:
#     #             with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
#     #                 data = json.load(f)
#     #                 return data.get("history1", []), data.get("history2", [])
#     #         except Exception as e:
#     #             messagebox.showerror("错误", f"加载搜索历史失败: {e}")
#     #     return [], []
#     def load_search_history(self):
#         """从文件加载"""
#         if os.path.exists(SEARCH_HISTORY_FILE):
#             try:
#                 with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
#                     data = json.load(f)
#                     h1, h2 = data.get("history1", []), data.get("history2", [])
#                     # 升级旧数据格式（字符串 -> dict）
#                     h1 = [self._normalize_record(r) for r in h1]
#                     h2 = [self._normalize_record(r) for r in h2]
#                     return h1, h2
#             except Exception as e:
#                 messagebox.showerror("错误", f"加载搜索历史失败: {e}")
#         return [], []

#     def _normalize_record(self, r):
#         """兼容旧数据格式，保证返回 dict"""
#         if isinstance(r, str):
#             return {"query": r, "starred": False, "note": ""}
#         elif isinstance(r, dict):
#             return {
#                 "query": r.get("query", ""),
#                 "starred": r.get("starred", False),
#                 "note": r.get("note", "")
#             }
#         else:
#             return {"query": str(r), "starred": False, "note": ""}

#     # ========== 功能 ==========
#     def switch_group(self, event=None):
#         """切换 history1 / history2"""
#         sel = self.combo_group.get()
#         if sel == "history1":
#             self.current_history = self.history1
#             self.current_key = "history1"
#         else:
#             self.current_history = self.history2
#             self.current_key = "history2"
#         self.refresh_tree()

#     def add_query(self):
#         query = self.entry_query.get().strip()
#         if not query:
#             messagebox.showwarning("提示", "请输入 Query")
#             return
#         self.current_history.insert(0, {"query": query, "starred": False, "note": ""})
#         self.refresh_tree()
#         self.entry_query.delete(0, tk.END)
#         self.save_search_history()

#     def on_click_star(self, event):
#         """单击星标列切换"""
#         region = self.tree.identify("region", event.x, event.y)
#         if region != "cell":
#             return
#         col = self.tree.identify_column(event.x)
#         if col != "#2":  # 第二列是 star
#             return
#         row_id = self.tree.identify_row(event.y)
#         if not row_id:
#             return
#         idx = int(row_id) - 1
#         if 0 <= idx < len(self.current_history):
#             self.current_history[idx]["starred"] = not self.current_history[idx]["starred"]
#             self.refresh_tree()
#             self.save_search_history()

#     def on_double_click(self, event):
#         """双击修改 Query 或 Note"""
#         region = self.tree.identify("region", event.x, event.y)
#         if region != "cell":
#             return

#         col = self.tree.identify_column(event.x)
#         row_id = self.tree.identify_row(event.y)
#         if not row_id:
#             return
#         idx = int(row_id) - 1
#         record = self.current_history[idx]

#         if col == "#1":  # Query 列
#             new_q = simpledialog.askstring("修改 Query", "请输入新的 Query：", initialvalue=record["query"])
#             if new_q is not None and new_q.strip():
#                 record["query"] = new_q.strip()
#                 self.refresh_tree()
#                 self.save_search_history()
#         elif col == "#3":  # Note 列
#             new_note = simpledialog.askstring("修改备注", "请输入新的备注：", initialvalue=record["note"])
#             if new_note is not None:
#                 record["note"] = new_note
#                 self.refresh_tree()
#                 self.save_search_history()

#     def use_query(self):
#         item = self.tree.selection()
#         if not item:
#             return
#         idx = int(item[0]) - 1
#         query = self.current_history[idx]["query"]
#         messagebox.showinfo("使用 Query", f"使用：\n{query}")

#     def refresh_tree(self):
#         self.tree.delete(*self.tree.get_children())
#         for idx, record in enumerate(self.current_history, start=1):
#             star = "⭐" if record.get("starred") else ""
#             note = record.get("note", "")
#             self.tree.insert("", "end", iid=str(idx), values=(record.get("query", ""), star, note))


# if __name__ == "__main__":
#     root = tk.Tk()
#     app = QueryHistoryManager(root)
#     root.mainloop()



import tkinter as tk
from tkinter import ttk, messagebox
import json, os

SEARCH_HISTORY_FILE = "search_history.json"

class QueryHistoryManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Query History Manager")

        self.history1, self.history2 = self.load_search_history()
        self.current_history = self.history1
        self.current_key = "history1"

        # --- 输入区 ---
        frame_input = tk.Frame(root)
        frame_input.pack(fill="x", padx=5, pady=5)

        tk.Label(frame_input, text="Query:").pack(side="left")
        self.entry_query = tk.Entry(frame_input)
        self.entry_query.pack(side="left", fill="x", expand=True, padx=5)

        btn_add = tk.Button(frame_input, text="保存", command=self.add_query)
        btn_add.pack(side="left", padx=5)

        self.combo_group = ttk.Combobox(frame_input, values=["history1", "history2"], state="readonly", width=10)
        self.combo_group.set("history1")
        self.combo_group.pack(side="left", padx=5)
        self.combo_group.bind("<<ComboboxSelected>>", self.switch_group)

        # --- Treeview ---
        self.tree = ttk.Treeview(root, columns=("query", "star", "note"), show="headings")
        self.tree.heading("query", text="Query")
        self.tree.heading("star", text="⭐")
        self.tree.heading("note", text="备注")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        # 双击填入输入框编辑
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-1>", self.on_click_star)

        # --- 使用按钮 ---
        frame_btn = tk.Frame(root)
        frame_btn.pack(fill="x", padx=5, pady=5)
        tk.Button(frame_btn, text="使用选中Query", command=self.use_query).pack(side="left", padx=5)

        # 绑定窗口大小变化事件，自适应列宽
        root.bind("<Configure>", self.on_resize)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.refresh_tree()

    # ================= 数据存取 =================
    def save_search_history(self):
        try:
            data = {"history1": self.history1, "history2": self.history2}
            with open(SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("错误", f"保存搜索历史失败: {e}")

    def load_search_history(self):
        if os.path.exists(SEARCH_HISTORY_FILE):
            try:
                with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    h1 = [self._normalize_record(r) for r in data.get("history1", [])]
                    h2 = [self._normalize_record(r) for r in data.get("history2", [])]
                    return h1, h2
            except Exception as e:
                messagebox.showerror("错误", f"加载搜索历史失败: {e}")
        return [], []

    def _normalize_record(self, r):
        if isinstance(r, str):
            return {"query": r, "starred": False, "note": ""}
        elif isinstance(r, dict):
            return {"query": r.get("query", ""), "starred": r.get("starred", False), "note": r.get("note", "")}
        else:
            return {"query": str(r), "starred": False, "note": ""}

    # ================= 功能 =================
    def switch_group(self, event=None):
        sel = self.combo_group.get()
        self.current_history = self.history1 if sel == "history1" else self.history2
        self.current_key = sel
        self.refresh_tree()

    def edit_query(self, idx, new_query):
        """
        编辑 current_history 中的某条 query
        idx: 要编辑的条目索引
        new_query: 新的 query 字符串
        """
        if not new_query.strip():
            messagebox.showwarning("提示", "请输入 Query")
            return

        # 更新 current_history
        self.current_history[idx]["query"] = new_query

        # 刷新 Treeview
        self.refresh_tree()

        # 同步主视图 Combobox
        if self.current_key == "history1":
            self.history1 = [{"query": r["query"], "starred": r["starred"], "note": r["note"]} for r in self.current_history]
            self.search_history1 = [r["query"] for r in self.history1]
            self.search_combo1['values'] = self.search_history1
            self.search_var1.set(new_query)
        else:
            self.history2 = [{"query": r["query"], "starred": r["starred"], "note": r["note"]} for r in self.current_history]
            self.search_history2 = [r["query"] for r in self.current_history]
            self.search_combo2['values'] = self.search_history2
            self.search_var2.set(new_query)

        # 保存历史
        self.save_search_history()


    def add_query(self):
        query = self.entry_query.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入 Query")
            return
        if hasattr(self, "editing_idx") and self.editing_idx is not None:
            self.current_history[self.editing_idx]["query"] = query
            self.editing_idx = None
        else:
            self.current_history.insert(0, {"query": query, "starred": False, "note": ""})
        self.entry_query.delete(0, tk.END)
        self.refresh_tree()
        self.save_search_history()

    def on_click_star(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#2":
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        idx = int(row_id) - 1
        if 0 <= idx < len(self.current_history):
            self.current_history[idx]["starred"] = not self.current_history[idx]["starred"]
            self.refresh_tree()
            self.save_search_history()

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        self.tree.selection_set(item)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="删除", command=lambda: self.delete_item(item))
        menu.add_command(label="置顶", command=lambda: self.move_to_top(item))
        menu.add_command(label="导出", command=lambda: self.export_item(item))
        menu.tk_popup(event.x_root, event.y_root)

    def delete_item(self, iid):
        idx = int(iid)
        self.history.pop(idx)
        self.save_history()
        self.refresh_tree()

    def move_to_top(self, iid):
        idx = int(iid)
        record = self.history.pop(idx)
        self.history.insert(0, record)
        self.save_history()
        self.refresh_tree()

    def on_double_click(self, event):

        """双击修改 Query 或 Note"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        idx = int(row_id) - 1
        record = self.current_history[idx]
        if col == "#3":  # Note 列
            new_note = simpledialog.askstring("修改备注", "请输入新的备注：", initialvalue=record["note"])
            if new_note is not None:
                record["note"] = new_note
                self.refresh_tree()
                self.save_search_history()

        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        idx = int(row_id) - 1
        self.editing_idx = idx
        record = self.current_history[idx]
        self.entry_query.delete(0, tk.END)
        self.entry_query.insert(0, record["query"])

        # row_id = self.tree.identify_row(event.y)
        # if not row_id:
        #     return
        # idx = int(row_id) - 1
        # self.editing_idx = idx
        # record = self.current_history[idx]
        # self.entry_query.delete(0, tk.END)
        # self.entry_query.insert(0, record["query"])

    def use_query(self):
        item = self.tree.selection()
        if not item:
            return
        idx = int(item[0]) - 1
        query = self.current_history[idx]["query"]
        messagebox.showinfo("使用 Query", f"使用：\n{query}")

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for idx, record in enumerate(self.current_history, start=1):
            star = "⭐" if record.get("starred") else ""
            note = record.get("note", "")
            self.tree.insert("", "end", iid=str(idx), values=(record.get("query", ""), star, note))
        self.adjust_column_widths()

    def on_resize(self, event=None):
        self.adjust_column_widths()

    def adjust_column_widths(self):
        total_width = self.tree.winfo_width()
        star_width = 40
        note_width = 200
        query_width = max(total_width - star_width - note_width - 10, 100)
        self.tree.column("query", width=query_width)
        self.tree.column("star", width=star_width)
        self.tree.column("note", width=note_width)


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("900x500")
    app = QueryHistoryManager(root)
    root.mainloop()
