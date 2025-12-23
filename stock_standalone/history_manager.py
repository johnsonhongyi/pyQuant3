import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import re
import platform
import ctypes
try:
    import win32api
except ImportError:
    win32api = None

from JohnsonUtil import LoggerFactory
from gui_utils import askstring_at_parent_single,clamp_window_to_screens
from stock_logic_utils import test_code_against_queries,toast_message

logger = LoggerFactory.getLogger('QueryHistoryManager')

# def toast_message(master, text, duration=1500):
#     """短暂提示信息（浮层，不阻塞）"""
#     toast = tk.Toplevel(master)
#     toast.overrideredirect(True)
#     toast.attributes("-topmost", True)
#     label = tk.Label(toast, text=text, bg="black", fg="white", padx=10, pady=1)
#     label.pack()
#     try:
#         master.update_idletasks()
#         master_x = master.winfo_rootx()
#         master_y = master.winfo_rooty()
#         master_w = master.winfo_width()
#     except Exception:
#         master_x, master_y, master_w = 100, 100, 400
#     toast.update_idletasks()
#     toast_w = toast.winfo_width()
#     toast_h = toast.winfo_height()
#     toast.geometry(f"{toast_w}x{toast_h}+{master_x + (master_w-toast_w)//2}+{master_y + 50}")
#     toast.after(duration, toast.destroy)

class QueryHistoryManager:
    def __init__(self, root=None, search_var1=None, search_var2=None, search_var3=None,
                 search_combo1=None, search_combo2=None, search_combo3=None,
                 auto_run=False, history_file="query_history.json",
                 sync_history_callback=None, test_callback=None):
        """
        root=None 时不创建窗口，只管理数据
        auto_run=True 时直接打开编辑窗口
        """
        self.root = root
        self.history_file = history_file
        self.search_var1 = search_var1
        self.search_var2 = search_var2
        self.search_var3 = search_var3
        self.his_limit = 30
        self.search_combo1 = search_combo1
        self.search_combo2 = search_combo2
        self.search_combo3 = search_combo3
        self.deleted_stack = []  # 保存被删除的 query 记录

        self.sync_history_callback = sync_history_callback
        self.test_callback = test_callback
        # 读取历史
        self.history1, self.history2, self.history3 = self.load_search_history()
        self.current_history = self.history1
        self.current_key = "history1"
        self.MAX_HISTORY = 500
        self._build_ui()

    def _build_ui(self):
        if not self.root:
            return
            
        if hasattr(self, "editor_frame"):
            self.editor_frame.destroy()  # 重建

        self.editor_frame = tk.Frame(self.root)
        frame_input = tk.Frame(self.editor_frame)
        frame_input.pack(fill="x", padx=5, pady=1, expand=True)

        tk.Label(frame_input, text="Query:").pack(side="left")
        self.entry_query = tk.Entry(frame_input)
        self.entry_query.pack(side="left", padx=5, fill="x", expand=True)

        tk.Button(frame_input, text="测试", command=self.on_test_click).pack(side="left", padx=2)
        tk.Button(frame_input, text="添加", command=self.add_query).pack(side="left", padx=5)
        tk.Button(frame_input, text="使用选中", command=self.use_query).pack(side="left", padx=5)
        tk.Button(frame_input, text="保存", command=self.save_search_history).pack(side="right", padx=5)

        self.entry_query.bind("<Button-3>", self.on_right_click)

        self.combo_group = ttk.Combobox(
            frame_input,
            values=["history1", "history2", "history3"],
            state="readonly", width=10
        )
        self.combo_group.set("history1")
        self.combo_group.pack(side="left", padx=5, ipady=1)
        self.combo_group.bind("<<ComboboxSelected>>", self.switch_group)

        self.tree = ttk.Treeview(
            self.editor_frame, columns=("query", "star", "note", "hit"), show="headings", height=12
        )
        self.tree.heading("query", text="Query")
        self.tree.heading("star", text="⭐")
        self.tree.heading("note", text="备注")
        self.tree.heading("hit", text="命中")

        col_ratios = {"query": 0.7, "star": 0.05, "note": 0.2, "hit": 0.05}

        for col in self.tree["columns"]:
            self.tree.column(col, width=1, anchor="w", stretch=True)

        self.tree.pack(expand=True, fill="both")

        def adjust_column_widths():
            if not hasattr(self, "tree") or not self.tree.winfo_exists():
                return
            total_width = self.tree.winfo_width()
            if total_width <= 1:
                self.tree.after(50, adjust_column_widths)
                return
            for col, ratio in col_ratios.items():
                self.tree.column(col, width=int(total_width * ratio))

        self.tree.after(50, adjust_column_widths)

        def on_resize(event):
            total_width = event.width
            for col, ratio in col_ratios.items():
                self.tree.column(col, width=int(total_width * ratio))

        self.editor_frame.bind("<Configure>", on_resize)

        self.tree.bind("<Button-1>", self.on_click_star)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Delete>", self.on_delete_key)

        self.root.bind("<Control-z>", self.undo_delete)
        self.root.bind("<Escape>", lambda event: self.open_editor())
        self.root.bind("<Alt-q>", lambda event: self.open_editor())

        for col in ("query", "star", "note", "hit"):
            self.tree.heading(col, text=col.capitalize(), command=lambda _col=col: self.treeview_sort_column(self.tree, _col))

        self.refresh_tree()

    def on_right_click(self, event):
        try:
            clipboard_text = event.widget.clipboard_get()
        except tk.TclError:
            return
        if clipboard_text.find('and') < 0:
            match = re.search(r'\b\d{6}\b', clipboard_text)
            if match:
                code = match.group(0)
                event.widget.delete(0, tk.END)
                event.widget.insert(0, code)
                self.on_test_click()
            else:
                logger.info(f"[on_right_click] 未找到6位数字代码: {clipboard_text}")
        else:
            event.widget.delete(0, tk.END)
            event.widget.insert(0, clipboard_text)
            self.on_test_click()

    def treeview_sort_column(self, tv, col, reverse=False):
        data_list = [(tv.set(k, col), k) for k in tv.get_children('')]
        try:
            data_list.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError:
            data_list.sort(key=lambda t: t[0], reverse=reverse)
        for index, (val, k) in enumerate(data_list):
            tv.move(k, '', index)
        tv.heading(col, command=lambda: self.treeview_sort_column(tv, col, not reverse))

    def open_editor(self):
        if not hasattr(self, "editor_frame"):
            self._build_ui()
            self.editor_frame.pack(fill="both", expand=True)
        else:
            if self.editor_frame.winfo_ismapped():
                self.editor_frame.pack_forget()
            else:
                self.editor_frame.pack(fill="both", expand=True)

    def save_search_history(self, confirm_threshold=10):
        try:
            def dedup(history):
                seen = set()
                result = []
                for r in history:
                    q = r.get("query") if isinstance(r, dict) else str(r)
                    if q not in seen:
                        seen.add(q)
                        result.append(r)
                return result

            def normalize_history(history):
                normalized = []
                for r in history:
                    if not isinstance(r, dict):
                        continue
                    q = r.get("query", "")
                    starred = r.get("starred", 0)
                    note = r.get("note", "")
                    if isinstance(starred, bool):
                        starred = 1 if starred else 0
                    elif not isinstance(starred, int):
                        starred = 0
                    normalized.append({"query": q, "starred": starred, "note": note})
                return normalized

            def merge_history(current, old):
                seen = set()
                result = []
                for r in current:
                    q = r.get("query") if isinstance(r, dict) else str(r)
                    if q not in seen:
                        seen.add(q)
                        result.append(r)
                for r in old:
                    q = r.get("query") if isinstance(r, dict) else str(r)
                    if q not in seen:
                        seen.add(q)
                        result.append(r)
                return result[:self.MAX_HISTORY]

            old_data = {"history1": [], "history2": [], "history3": []}
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    try:
                        loaded_data = json.load(f)
                        old_data["history1"] = dedup(loaded_data.get("history1", []))
                        old_data["history2"] = dedup(loaded_data.get("history2", []))
                        old_data["history3"] = dedup(loaded_data.get("history3", []))
                    except json.JSONDecodeError:
                        pass

            self.history1 = normalize_history(self.history1)
            self.history2 = normalize_history(self.history2)
            self.history3 = normalize_history(self.history3)

            merged_data = {
                "history1": normalize_history(merge_history(self.history1, old_data.get("history1", []))),
                "history2": normalize_history(merge_history(self.history2, old_data.get("history2", []))),
                "history3": normalize_history(merge_history(self.history3, old_data.get("history3", []))),
            }

            def changes_count(old_list, new_list):
                old_set = {r['query'] for r in old_list}
                new_set = {r['query'] for r in new_list}
                return len(new_set - old_set) + len(old_set - new_set)

            delta1 = changes_count(old_data.get("history1", []), merged_data["history1"])
            delta2 = changes_count(old_data.get("history2", []), merged_data["history2"])

            if delta1 + delta2 >= confirm_threshold:
                if not messagebox.askyesno("确认保存", f"搜索历史发生较大变动（{delta1 + delta2} 条），是否继续保存？"):
                    logger.info("❌ 用户取消保存搜索历史")
                    return

            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 搜索历史已保存 (h1: {len(merged_data['history1'])} / h2: {len(merged_data['history2'])} / h3: {len(merged_data['history3'])})")

        except Exception as e:
            messagebox.showerror("错误", f"保存搜索历史失败: {e}")

    def load_search_history(self):
        h1, h2, h3 = [], [], []
        upgraded = False
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                def normalize_starred_field(history_list):
                    nonlocal upgraded
                    for r in history_list:
                        val = r.get("starred", 0)
                        if isinstance(val, bool):
                            r["starred"] = 1 if val else 0
                            upgraded = True
                        elif not isinstance(val, int):
                            r["starred"] = 0
                            upgraded = True

                def dedup(history):
                    seen = set()
                    result = []
                    for r in history:
                        q = r.get("query", "")
                        if q not in seen:
                            seen.add(q)
                            result.append(r)
                    return result

                raw_h1 = [self._normalize_record(r) for r in data.get("history1", [])]
                raw_h2 = [self._normalize_record(r) for r in data.get("history2", [])]
                raw_h3 = [self._normalize_record(r) for r in data.get("history3", [])]

                normalize_starred_field(raw_h1)
                normalize_starred_field(raw_h2)
                normalize_starred_field(raw_h3)

                raw_h1, raw_h2, raw_h3 = map(dedup, (raw_h1, raw_h2, raw_h3))

                h1 = raw_h1[:self.his_limit]
                h2 = raw_h2[:self.his_limit]
                h3 = raw_h3[:self.his_limit]

                if upgraded:
                    with open(self.history_file, "w", encoding="utf-8") as f:
                        json.dump({"history1": raw_h1, "history2": raw_h2, "history3": raw_h3}, f, ensure_ascii=False, indent=2)
                    logger.info("✅ 自动升级 search_history.json，starred 字段格式已统一")
            except Exception as e:
                messagebox.showerror("错误", f"加载搜索历史失败: {e}")
        return h1, h2, h3

    def _normalize_record(self, r):
        if isinstance(r, dict):
            q = r.get("query", "")
            try:
                q_dict = eval(q)
                if isinstance(q_dict, dict) and "query" in q_dict:
                    q = q_dict["query"]
            except:
                pass
            return {"query": q, "starred": r.get("starred", False), "note": r.get("note", "")}
        elif isinstance(r, str):
            return {"query": r, "starred": 0, "note": ""}
        else:
            return {"query": str(r), "starred": 0, "note": ""}

    def switch_group(self, event=None):
        self.clear_hits()
        if getattr(self, "_suppress_switch", False):
            return
        sel = self.combo_group.get()
        if sel == "history1":
            self.current_history = self.history1
            self.current_key = "history1"
        elif sel == "history2":
            self.current_history = self.history2
            self.current_key = "history2"
        elif sel == "history3":
            self.current_history = self.history3
            self.current_key = "history3"
        logger.info(f"[SWITCH] 当前分组切换到：{sel}")
        self.refresh_tree()

    def edit_query(self, iid):
        values = self.tree.item(iid, "values")
        if not values:
            return
        current_query = values[0]
        idx = next((i for i, r in enumerate(self.current_history) if r.get("query") == current_query), None)
        if idx is None:
            return
        record = self.current_history[idx]
        new_query = askstring_at_parent_single(self.root, "修改 Query", "请输入新的 Query：", initialvalue=record.get("query", ""))
        if new_query and new_query.strip():
            new_query = new_query.strip()
            old_query = record["query"]
            if self.current_key == "history1":
                self.history1[idx]["query"] = new_query
            elif self.current_key == "history2":
                self.history2[idx]["query"] = new_query
            elif self.current_key == "history3":
                self.history3[idx]["query"] = new_query
                if hasattr(self, "sync_history_callback") and callable(self.sync_history_callback):
                    try:
                        self.sync_history_callback(search_history3=self.history3)
                        self.refresh_tree()
                    except Exception as e:
                        logger.info(f"[警告] 同步 search_history3 失败: {e}")
            self._just_edited_query = (old_query, new_query)
            self.refresh_tree()
            self.use_query(new_query)

    def add_query(self):
        query = self.entry_query.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入 Query")
            return
        if query.isdigit() or len(query) == 6:
            toast_message(self.root, "股票代码仅测试使用")
            return
        existing = next((item for item in self.current_history if item["query"] == query), None)
        if existing:
            if existing.get("starred", 0) > 0 or existing.get("note", "").strip():
                self.current_history.remove(existing)
                self.current_history.insert(0, existing)
            else:
                self.current_history.remove(existing)
                self.current_history.insert(0, {"query": query, "starred": 0, "note": ""})
        else:
            self.current_history.insert(0, {"query": query, "starred": 0, "note": ""})
        if self.current_key == "history1":
            self.history1 = self.current_history
        elif self.current_key == "history2":
            self.history2 = self.current_history
        elif self.current_key == "history3":
            self.history3 = self.current_history
        self.refresh_tree()
        self.entry_query.delete(0, tk.END)
        self.use_query(query)

    def on_click_star(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell": return
        col = self.tree.identify_column(event.x)
        if col != "#2": return
        row_id = self.tree.identify_row(event.y)
        if not row_id: return
        idx = int(row_id) - 1
        if 0 <= idx < len(self.current_history):
            record = self.current_history[idx]
            old_val = record.get("starred", 0)
            if isinstance(old_val, bool): old_val = 1 if old_val else 0
            record["starred"] = (old_val + 1) % 5
            self.refresh_tree() 

    def get_centered_window_position_query(self, parent, win_width, win_height, margin=10):
        mx = parent.winfo_pointerx()
        my = parent.winfo_pointery()
        scale = 1
        win_width = int(win_width * scale)
        win_height = int(win_height * scale)
        x = mx + margin
        y = my - win_height // 2
        monitors = []
        if win32api:
            try:
                for handle_tuple in win32api.EnumDisplayMonitors():
                    info = win32api.GetMonitorInfo(handle_tuple[0])
                    monitors.append(info["Monitor"])
            except Exception as e:
                logger.info(f"[WARN] 获取显示器信息失败: {e}")
        if not monitors:
            if win32api:
                screen_width = win32api.GetSystemMetrics(0)
                screen_height = win32api.GetSystemMetrics(1)
            else:
                screen_width, screen_height = 1920, 1080
            monitors = [(0, 0, screen_width, screen_height)]
        hit_monitor = None
        for left, top, right, bottom in monitors:
            if left <= mx < right and top <= my < bottom:
                hit_monitor = (left, top, right, bottom)
                break
        if hit_monitor:
            left, top, right, bottom = hit_monitor
            if x + win_width > right: x = mx - win_width - margin
            x = max(left, min(x, right - win_width))
            y = max(top, min(y, bottom - win_height))
        else:
            main_left, main_top, main_right, main_bottom = monitors[0]
            x = main_left + (main_right - main_left - win_width) // 2
            y = main_top + (main_bottom - main_top - win_height) // 2
        return int(x), int(y)

    def askstring_at_parent(self, parent, title, prompt, initialvalue=""):
        dlg = tk.Toplevel(parent)
        dlg.transient(parent)
        dlg.title(title)
        dlg.resizable(True, True)
        if win32api:
            screen_width = win32api.GetSystemMetrics(0)
        else:
            screen_width = 1920
        screen_width_limit = screen_width * 0.8
        char_width = 10
        scale_factor = getattr(self.root, 'scale_factor', 1.0)
        min_width = int(400 * scale_factor)
        max_width = 2000 if 1000 * scale_factor < screen_width_limit else screen_width_limit
        win_width = max(min_width, min(len(initialvalue) * char_width + 100, max_width))
        win_height = 120
        x, y = self.get_centered_window_position_query(parent, win_width, win_height)
        dlg.geometry(f"{int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")
        result = {"value": None}
        lbl = tk.Label(dlg, text=prompt, anchor="w", justify="left", wraplength=int(win_width * 0.9))
        lbl.pack(pady=(10, 6), padx=10, fill="x")
        entry = ttk.Entry(dlg)
        entry.pack(padx=10, pady=(0, 10), fill="both", expand=True)
        entry.insert(0, initialvalue)
        entry.focus_set()
        frame_btn = tk.Frame(dlg)
        frame_btn.pack(pady=(0, 10))
        def on_ok():
            result["value"] = entry.get()
            dlg.destroy()
        def on_cancel(): dlg.destroy()
        tk.Button(frame_btn, text="确定", width=10, command=on_ok).pack(side="left", padx=6)
        tk.Button(frame_btn, text="取消", width=10, command=on_cancel).pack(side="left", padx=6)
        dlg.bind("<Escape>", lambda e: on_cancel())
        dlg.bind("<Return>", lambda e: on_ok())
        dlg.grid_rowconfigure(1, weight=1)
        dlg.grid_columnconfigure(0, weight=1)
        dlg.grab_set()
        parent.wait_window(dlg)
        return result["value"]

    def on_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell": return
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id: return
        values = self.tree.item(row_id, 'values')
        if not values: return
        query_text = values[0]
        idx = next((i for i, r in enumerate(self.current_history) if r.get("query") == query_text), None)
        if idx is None:
            try: idx = int(row_id) - 1
            except: return
        record = self.current_history[idx]
        if col == "#3":
            new_note = self.askstring_at_parent(self.root, "修改备注", "请输入新的备注：", initialvalue=record.get("note", ""))
            if new_note is not None:
                record["note"] = new_note
                if self.current_key == "history1": self.history1[idx]["note"] = new_note
                elif self.current_key == "history2": self.history2[idx]["note"] = new_note
                elif self.current_key == "history3": self.history3[idx]["note"] = new_note
                self.current_history[idx]["note"] = new_note
                self.refresh_tree()
            return
        self.use_query(record["query"])

    def use_query(self, query=None):
        if query is None:
            item = self.tree.selection()
            if not item: return
            idx = int(item[0]) - 1
            if idx < 0 or idx >= len(self.current_history): return
            query = self.current_history[idx]["query"]
        if self.current_key == "history1":
            if self.search_var1: self.search_var1.set(query)
            if self.search_combo1 and query not in self.search_combo1["values"]:
                values = list(self.search_combo1["values"])
                values.insert(0, query)
                self.search_combo1["values"] = values
        elif self.current_key == "history2":
            if self.search_var2: self.search_var2.set(query)
            if self.search_combo2 and query not in self.search_combo2["values"]:
                values = list(self.search_combo2["values"])
                values.insert(0, query)
                self.search_combo2["values"] = values
        elif self.current_key == "history3":
            history_list = self.current_history
            idx = next((i for i, item in enumerate(history_list) if item.get("query") == query), None)
            if idx is not None and idx != 0:
                item = history_list.pop(idx)
                history_list.insert(0, item)
            elif idx is None:
                history_list.insert(0, {"query": query, "starred": 0, "note": ""})
            self.current_history = history_list
            self.history3 = self.current_history
            if hasattr(self, "sync_history_callback") and callable(self.sync_history_callback):
                try:
                    self.sync_history_callback(search_history3=self.history3)
                    self.refresh_tree()
                except Exception as e:
                    logger.info(f"[警告] 同步 search_history3 失败: {e}")

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item: return
        self.tree.selection_set(item)
        menu = tk.Menu(self.editor_frame, tearoff=0)
        menu.add_command(label="使用", command=lambda: self.use_query())
        menu.add_command(label="编辑Query", command=lambda: self.edit_query(item))
        menu.add_command(label="编辑框", command=lambda: self.up_to_entry(item))
        menu.add_command(label="删除", command=lambda: self.delete_item(item))
        menu.tk_popup(event.x_root, event.y_root)

    def on_delete_key(self, event):
        selected = self.tree.selection()
        if selected: self.delete_item(selected[0])

    def sync_history_current(self, record, action="delete", history_key=None):
        if history_key is None: history_key = self.current_key
        query = record.get("query")
        if not query: return
        if history_key == "history1": combo, var, target = self.search_combo1, self.search_var1, self.history1
        elif history_key == "history2": combo, var, target = self.search_combo2, self.search_var2, self.history2
        elif history_key == "history3": combo, var, target = self.search_combo3, self.search_var3, self.history3
        else: return
        if action == "delete":
            target[:] = [r for r in target if r.get("query") != query]
            if combo: combo['values'] = [r.get("query") for r in target]
            if var and var.get() == query: var.set("")
        elif action == "add":
            if not any(r.get("query") == query for r in target): target.insert(0, record.copy())
            if combo: combo['values'] = [r.get("query") for r in target]
        if callable(self.sync_history_callback):
            if hasattr(self.root, "_suppress_sync") and self.root._suppress_sync: return
            try:
                if history_key == "history1": self.sync_history_callback(search_history1=self.history1)
                elif history_key == "history2": self.sync_history_callback(search_history2=self.history2)
                elif history_key == "history3": self.sync_history_callback(search_history3=self.history3)
            except Exception as e: logger.info(f"[SYNC ERR] {e}")
        suppress_state = getattr(self, "_suppress_switch", False)
        self._suppress_switch = True
        try: self.refresh_tree()
        finally: self._suppress_switch = suppress_state

    def delete_item(self, iid):
        idx = int(iid) - 1
        if not (0 <= idx < len(self.current_history)): return
        record = self.current_history.pop(idx)
        history_key = self.current_key
        self.deleted_stack.append({"record": record.copy(), "history_key": history_key, "index": idx})
        self._suppress_switch = True
        self.sync_history_current(record, action="delete", history_key=history_key)
        self.refresh_tree()
        self._suppress_switch = False
        logger.info(f"[DEL] 从 {history_key} 删除 {record.get('query')}")

    def undo_delete(self, event=None):
        if not self.deleted_stack:
            toast_message(self.root, "没有可撤销的记录", 1200)
            return
        last_deleted = self.deleted_stack.pop()
        record = last_deleted["record"]
        history_key = last_deleted["history_key"]
        index = last_deleted["index"]
        if history_key == "history1": target_history = self.history1
        elif history_key == "history2": target_history = self.history2
        elif history_key == "history3": target_history = self.history3
        else: return
        if any(r.get("query") == record.get("query") for r in target_history):
            toast_message(self.root, f"已存在：{record.get('query')}", 1200)
            return
        if 0 <= index <= len(target_history): target_history.insert(index, record)
        else: target_history.insert(0, record)
        self.sync_history_current(record, action="add", history_key=history_key)
        toast_message(self.root, f"已恢复：{record.get('query')}", 1500)

    def up_to_entry(self, iid):
        values = self.tree.item(iid, "values")
        if not values: return
        current_query = values[0]
        idx = next((i for i, r in enumerate(self.current_history) if r.get("query") == current_query), None)
        if idx is None: return
        record = self.current_history[idx]
        self.entry_query.delete(0, tk.END)
        self.entry_query.insert(0, record["query"])

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.tree.tag_configure("hit", background="#d1ffd1")
        self.tree.tag_configure("miss", background="#ffd1d1")
        self.tree.tag_configure("normal", background="#ffffff")
        for idx, record in enumerate(self.current_history, start=1):
            star_count = record.get("starred", 0)
            if isinstance(star_count, bool): star_count = 1 if star_count else 0
            star_text = "★" * star_count
            hit = record.get("hit", None)
            if isinstance(hit, int):
                if hit == 0: hit_text, tag = "❌", "miss"
                elif hit == 1: hit_text, tag = "✅", "hit"
                else: hit_text, tag = str(hit), "hit"
            elif hit is True: hit_text, tag = "✅", "hit"
            elif hit is False: hit_text, tag = "❌", "miss"
            else: hit_text, tag = "", "normal"
            self.tree.insert("", "end", iid=str(idx), values=(record.get("query", ""), star_text, record.get("note", ""), hit_text), tags=(tag,))

    def clear_hits(self):
        for record in self.current_history: record.pop("hit", None)

    def on_test_click(self):
        import ipdb;ipdb.set_trace()
        
        if callable(self.test_callback): self.test_callback(onclick=True)

    def test_code(self, code_data):
        queries = getattr(self, "current_history", [])
        return test_code_against_queries(code_data, queries)
