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
from gui_utils import askstring_at_parent_single, clamp_window_to_screens, get_centered_window_position_mainWin
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
    def __init__(self, root=None, search_var1=None, search_var2=None, search_var3=None, search_var4=None, search_var5=None,
                 search_combo1=None, search_combo2=None, search_combo3=None, search_combo4=None, search_combo5=None,
                 auto_run=False, history_file="query_history.json",
                 sync_history_callback=None, test_callback=None, df_all=None):
        """
        root=None 时不创建窗口，只管理数据
        auto_run=True 时直接打开编辑窗口
        """
        self.root = root
        self.history_file = history_file
        self.df_all = df_all
        self.search_var1 = search_var1
        self.search_var2 = search_var2
        self.search_var3 = search_var3
        self.search_var4 = search_var4
        self.search_var5 = search_var5
        self.his_limit = 30
        self.search_combo1 = search_combo1
        self.search_combo2 = search_combo2
        self.search_combo3 = search_combo3
        self.search_combo4 = search_combo4
        self.search_combo5 = search_combo5
        self.deleted_stack = []  # 保存被删除的 query 记录
        self._history_changed = False  # 追踪本次打开期间是否有过修改
        
        # [NEW] 状态展示变量，与主程序保持一致
        self.status_var = tk.StringVar(value="准备就绪")
        self.status_var2 = tk.StringVar(value="")

        self.sync_history_callback = sync_history_callback
        self.test_callback = test_callback
        # 读取历史
        self.history1, self.history2, self.history3, self.history4, self.history5 = self.load_search_history()
        self.current_history = self.history1
        self.current_key = "history1"
        self.MAX_HISTORY = 500
        self._build_ui()
        
        if auto_run:
            self.open_editor()

    def _dedup(self, history):
        """通用去重逻辑 (基于 query 和 note)"""
        seen_q = set()
        seen_n = set()
        result = []
        for r in history:
            if not isinstance(r, dict):
                q = str(r).strip()
                n = ""
                r = {"query": q, "starred": 0, "note": ""}
            else:
                q = r.get("query", "").strip()
                n = r.get("note", "").strip()
            
            if not q or q in seen_q:
                continue
            if n and n in seen_n:
                continue
            
            seen_q.add(q)
            if n: seen_n.add(n)
            result.append(r)
        return result

    def _normalize_history(self, history):
        """统一历史记录格式"""
        normalized = []
        seen_q = set()
        seen_n = set()
        for r in history:
            if not isinstance(r, dict):
                continue
            q = r.get("query", "").strip()
            if not q or q in seen_q:
                continue
            
            note = r.get("note", "").strip()
            if note and note in seen_n:
                continue

            seen_q.add(q)
            if note: seen_n.add(note)

            starred = r.get("starred", 0)
            if isinstance(starred, bool):
                starred = 1 if starred else 0
            elif not isinstance(starred, int):
                starred = 0
            normalized.append({"query": q, "starred": starred, "note": note})
        return normalized

    def _selective_merge(self, current, old):
        """
        ⭐ [BUGFIX] 内存态为权威：直接返回内存列表，不从磁盘补回已删除的记录。
        """
        return list(current)[:self.MAX_HISTORY]


    def _build_ui(self):
        if not self.root:
            return
            
        if hasattr(self, "editor_frame"):
            self.editor_frame.destroy()  # 重建

        self.editor_frame = tk.Frame(self.root)

        # [NEW] 全局搜索框
        frame_global_search = tk.Frame(self.editor_frame)
        frame_global_search.pack(fill="x", padx=5, pady=(5, 1))
        
        tk.Label(frame_global_search, text="🔍 全局搜索:").pack(side="left")
        self.entry_global_search = tk.Entry(frame_global_search)
        self.entry_global_search.pack(side="left", padx=5, fill="x", expand=True)
        self.entry_global_search.bind("<Return>", lambda e: self.do_global_search())
        tk.Button(frame_global_search, text="搜索所有历史", command=self.do_global_search).pack(side="left", padx=5)

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
            values=["history1", "history2", "history3", "history4", "history5"],
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

        # [NEW] 状态栏展示区: 展示匹配数及清理后的 Q 片段
        self.status_frame = tk.Frame(self.editor_frame)
        self.status_frame.pack(fill="x", side="bottom")
        tk.Label(self.status_frame, textvariable=self.status_var, fg="blue", font=("微软雅黑", 9)).pack(side="left", padx=5)
        tk.Label(self.status_frame, textvariable=self.status_var2, fg="darkgreen", font=("微软雅黑", 9)).pack(side="right", padx=5)

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
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

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

    def do_global_search(self):
        if not hasattr(self, "entry_global_search"):
            return
        keyword = self.entry_global_search.get().strip().lower()
        if not keyword:
            return
            
        # 💡 [关键改进] 从硬盘读取完整的历史记录进行全局搜索，绕过 UI 30 条的加载限制
        full_data = {}
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    full_data = json.load(f)
            except Exception as e:
                logger.error(f"[do_global_search] Read full file error: {e}")

        all_data = []
        for grp_name in ["history1", "history2", "history3", "history4", "history5"]:
            his_list = full_data.get(grp_name, [])
            for i, item in enumerate(his_list):
                if not isinstance(item, dict): continue
                q = item.get("query", "")
                n = item.get("note", "")
                if keyword in q.lower() or keyword in n.lower():
                    all_data.append({"id": i + 1, "group": grp_name, "query": q, "note": n})
                    
        if not all_data:
            toast_message(self.root, f"未找到包含 '{keyword}' 的记录")
            return
            
        top = tk.Toplevel(self.root)
        top.title(f"🔍 全局搜索结果: '{keyword}' - 共 {len(all_data)} 条")
        
        # 设置窗口大小并居中显示
        w, h = 1000, 500
        x, y = get_centered_window_position_mainWin(self.root, w, h)
        top.geometry(f"{w}x{h}+{x}+{y}")
        
        # 使用 ttk 样式增强
        main_frame = ttk.Frame(top, padding=5)
        main_frame.pack(fill="both", expand=True)

        # Treeview 结果列表
        col_ratios = {"id": 0.05, "group": 0.08, "query": 0.67, "note": 0.20}
        tree = ttk.Treeview(main_frame, columns=list(col_ratios.keys()), show="headings", selectmode="browse")
        
        # 应用系统统一的 Treeview 样式 (30px rowheight)
        style = ttk.Style()
        try:
            from dpi_utils import get_windows_dpi_scale_factor
            scale = get_windows_dpi_scale_factor()
        except:
            scale = 1.0
        style.configure("Treeview", rowheight=int(28 * scale)) 
        
        tree.heading("id", text="#", command=lambda: self.treeview_sort_column(tree, "id"))
        tree.heading("group", text="组", command=lambda: self.treeview_sort_column(tree, "group"))
        tree.heading("query", text="查询公式 (Query)", command=lambda: self.treeview_sort_column(tree, "query"))
        tree.heading("note", text="备注", command=lambda: self.treeview_sort_column(tree, "note"))
        
        # 初始宽度与对齐
        tree.column("id", width=int(w * 0.05), minwidth=40, anchor="center", stretch=False)
        tree.column("group", width=int(w * 0.08), minwidth=60, anchor="center", stretch=False)
        tree.column("query", width=int(w * 0.67), minwidth=400, stretch=True)
        tree.column("note", width=int(w * 0.20), minwidth=100, stretch=True)
        
        # 💡 响应式自适应
        def adjust_search_cols(event):
            tw = event.width - 25
            if tw > 200:
                tree.column("id", width=int(tw * 0.05))
                tree.column("group", width=int(tw * 0.08))
                tree.column("query", width=int(tw * 0.67))
                tree.column("note", width=int(tw * 0.20))
        
        top.bind("<Configure>", adjust_search_cols)

        # 滚动条
        vsb = ttk.Scrollbar(main_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        
        for d in all_data:
            disp_q = " ".join(d["query"].strip().split())
            if len(disp_q) > 250: disp_q = disp_q[:247] + "..."
            tree.insert("", "end", values=(d["id"], d["group"], disp_q, d["note"]))
            
        def on_pin_to_top():
            sel = tree.selection()
            if not sel: return
            idx = tree.index(sel[0])
            original_item = all_data[idx]
            q, n = original_item["query"], original_item["note"]
            
            existing_idx = -1
            for i, r in enumerate(self.current_history):
                if r.get("query") == q:
                    existing_idx = i; break
            if existing_idx >= 0: self.current_history.pop(existing_idx)
            self.current_history.insert(0, {"query": q, "starred": 0, "note": n})
            self._history_changed = True
            self.refresh_tree()
            self.save_search_history()
            toast_message(top, f"已置顶保存到当前的 {self.current_key} 第一个")
            
        def on_copy_info():
            sel = tree.selection()
            if not sel: return
            idx = tree.index(sel[0])
            q = all_data[idx]["query"]
            try:
                top.clipboard_clear(); top.clipboard_append(str(q))
                toast_message(top, "✅ Query公式已复制")
            except: pass

        def on_tree_double_click(event):
            region = tree.identify_region(event.x, event.y)
            if region != "cell": return
            column = tree.identify_column(event.x) # #1=id, #2=组, #3=Query, #4=备注
            sel = tree.selection()
            if not sel: return
            idx = tree.index(sel[0])
            item_data = all_data[idx]
            if column == "#4": # 备注列
                content, label = item_data.get("note", ""), "备注信息"
            else:
                content, label = item_data.get("query", ""), "Query公式"
            if content:
                try:
                    top.clipboard_clear(); top.clipboard_append(str(content))
                    toast_message(top, f"✅ {label}已复制")
                except: pass
        tree.bind("<Double-1>", on_tree_double_click)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=10)
        
        style = ttk.Style()
        style.configure("Primary.TButton", font=("微软雅黑", 10, "bold"))
        
        btn_pin = ttk.Button(btn_frame, text="📌 置顶保存到当前组第一行", command=on_pin_to_top, style="Primary.TButton")
        btn_pin.pack(side="left", padx=5)
        
        ttk.Button(btn_frame, text="📋 复制完整Query", command=on_copy_info).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="关闭窗口", command=top.destroy).pack(side="right", padx=5)

    def open_editor(self):
        # 每次打开时对数据重新读取一次存档,保持最新的数据
        will_show = True
        if hasattr(self, "editor_frame") and self.editor_frame.winfo_ismapped():
            will_show = False
            # 仅当本次打开期间有过修改时才自动保存
            if self._history_changed:
                logger.info("[open_editor] 检测到修改，自动保存历史记录...")
                self.save_search_history()
                self._history_changed = False
            
        if will_show:
            # 打开时重置修改标志
            self._history_changed = False
            try:
                self.history1, self.history2, self.history3, self.history4, self.history5 = self.load_search_history()
                if self.current_key == "history1": self.current_history = self.history1
                elif self.current_key == "history2": self.current_history = self.history2
                elif self.current_key == "history3": self.current_history = self.history3
                elif self.current_key == "history4": self.current_history = self.history4
                elif self.current_key == "history5": self.current_history = self.history5
                logger.info("[open_editor] History reloaded from disk.")
            except Exception as e:
                logger.error(f"[open_editor] Failed to reload history: {e}")

        if not hasattr(self, "editor_frame"):
            self._build_ui()
            self.editor_frame.pack(fill="both", expand=True)
        else:
            if not will_show:
                self.editor_frame.pack_forget()
            else:
                self.refresh_tree()
                self.editor_frame.pack(fill="both", expand=True)

    def save_search_history(self, confirm_threshold=10):
        try:
            old_data = {"history1": [], "history2": [], "history3": [], "history4": [], "history5": []}
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    try:
                        loaded_data = json.load(f)
                        old_data["history1"] = self._dedup(loaded_data.get("history1", []))
                        old_data["history2"] = self._dedup(loaded_data.get("history2", []))
                        old_data["history3"] = self._dedup(loaded_data.get("history3", []))
                        old_data["history4"] = self._dedup(loaded_data.get("history4", []))
                        old_data["history5"] = self._dedup(loaded_data.get("history5", []))
                    except json.JSONDecodeError:
                        pass

            self.history1 = self._normalize_history(self.history1)
            self.history2 = self._normalize_history(self.history2)
            self.history3 = self._normalize_history(self.history3)
            self.history4 = self._normalize_history(self.history4)
            self.history5 = self._normalize_history(self.history5)

            merged_data = {
                "history1": self._normalize_history(self._selective_merge(self.history1, old_data.get("history1", []))),
                "history2": self._normalize_history(self._selective_merge(self.history2, old_data.get("history2", []))),
                "history3": self._normalize_history(self._selective_merge(self.history3, old_data.get("history3", []))),
                "history4": self._normalize_history(self._selective_merge(self.history4, old_data.get("history4", []))),
                "history5": self._normalize_history(self._selective_merge(self.history5, old_data.get("history5", []))),
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

            # ⚙️ 关键：保存后同步内存状态，防止 history1/2/... 指向同一个对象或旧对象
            self.history1 = list(merged_data["history1"])
            self.history2 = list(merged_data["history2"])
            self.history3 = list(merged_data["history3"])
            self.history4 = list(merged_data["history4"])
            self.history5 = list(merged_data["history5"])
            
            # 更新当前引用
            if self.current_key == "history1": self.current_history = self.history1
            elif self.current_key == "history2": self.current_history = self.history2
            elif self.current_key == "history3": self.current_history = self.history3
            elif self.current_key == "history4": self.current_history = self.history4
            elif self.current_key == "history5": self.current_history = self.history5

            logger.info(f"✅ 搜索历史已保存 (h1: {len(self.history1)} / h2: {len(self.history2)} / h3: {len(self.history3)} / h4: {len(self.history4)} / h5: {len(self.history5)})")

        except Exception as e:
            messagebox.showerror("错误", f"保存搜索历史失败: {e}")

    def load_search_history(self):
        h1, h2, h3, h4, h5 = [], [], [], [], []
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

                raw_h1 = [self._normalize_record(r) for r in data.get("history1", [])]
                raw_h2 = [self._normalize_record(r) for r in data.get("history2", [])]
                raw_h3 = [self._normalize_record(r) for r in data.get("history3", [])]
                raw_h4 = [self._normalize_record(r) for r in data.get("history4", [])]
                raw_h5 = [self._normalize_record(r) for r in data.get("history5", [])]


                normalize_starred_field(raw_h1)
                normalize_starred_field(raw_h2)
                normalize_starred_field(raw_h3)
                normalize_starred_field(raw_h4)
                normalize_starred_field(raw_h5)

                h1 = list(raw_h1[:self.his_limit])
                h2 = list(raw_h2[:self.his_limit])
                h3 = list(raw_h3[:self.his_limit])
                h4 = list(raw_h4[:self.his_limit])
                h5 = list(raw_h5[:self.his_limit])

                if upgraded:
                    with open(self.history_file, "w", encoding="utf-8") as f:
                        json.dump({"history1": raw_h1, "history2": raw_h2, "history3": raw_h3, "history4": raw_h4, "history5": raw_h5}, f, ensure_ascii=False, indent=2)
                    logger.info("✅ 自动升级 search_history.json，starred 字段格式已统一")
            except Exception as e:
                logger.error(f"加载搜索历史失败: {e}")
        # 确保始终返回独立的列表对象
        return (list(h1), list(h2), list(h3), list(h4), list(h5))

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
        elif sel == "history4":
            self.current_history = self.history4
            self.current_key = "history4"
        elif sel == "history5":
            self.current_history = self.history5
            self.current_key = "history5"
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
        new_query = askstring_at_parent_single(self.root, "修改 Query", "请输入新的 Query：", initialvalue=record.get("query", ""), window_name="QueryHistoryManager_EditQuery")
        if new_query and new_query.strip():
            new_query = new_query.strip()
            old_query = record["query"]
            record["query"] = new_query
            self._history_changed = True  # 标记已修改
            
            # 同步回调以更新关联的 UI
            if callable(self.sync_history_callback):
                try:
                    key_num = self.current_key[-1] # "1", "2", "3", "4"
                    kwargs = {f"search_history{key_num}": self.current_history}
                    self.sync_history_callback(**kwargs)
                except Exception as e:
                    logger.info(f"[警告] 编辑同步 {self.current_key} 失败: {e}")

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
        elif self.current_key == "history4":
            self.history4 = self.current_history
        elif self.current_key == "history5":
            self.history5 = self.current_history
        self._history_changed = True  # 标记已修改
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
            self._history_changed = True  # 标记已修改
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
        win_height = 180
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
                elif self.current_key == "history4": self.history4[idx]["note"] = new_note
                elif self.current_key == "history5": self.history5[idx]["note"] = new_note
                self.current_history[idx]["note"] = new_note
                self._history_changed = True  # 标记已修改
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
            
        def move_to_top(history_list, q):
            idx = next((i for i, item in enumerate(history_list) if item.get("query") == q), None)
            if idx is not None:
                item = history_list.pop(idx)
                history_list.insert(0, item)
            else:
                history_list.insert(0, {"query": q, "starred": 0, "note": ""})
            return history_list

        if self.current_key == "history1":
            self.history1 = move_to_top(self.history1, query)
            if self.search_var1: self.search_var1.set(query)
            if self.search_combo1:
                vals = [r["query"] for r in self.history1]
                self.search_combo1["values"] = vals
            if callable(self.sync_history_callback):
                self.sync_history_callback(search_history1=self.history1, source="use", selected_query=query)
                
        elif self.current_key == "history2":
            self.history2 = move_to_top(self.history2, query)
            if self.search_var2: self.search_var2.set(query)
            if self.search_combo2:
                vals = [r["query"] for r in self.history2]
                self.search_combo2["values"] = vals
            if callable(self.sync_history_callback):
                self.sync_history_callback(search_history2=self.history2, source="use", selected_query=query)
                
        elif self.current_key == "history3":
            self.history3 = move_to_top(self.history3, query)
            if self.search_var3: self.search_var3.set(query)
            if self.search_combo3:
                vals = [r["query"] for r in self.history3]
                self.search_combo3["values"] = vals
            if callable(self.sync_history_callback):
                self.sync_history_callback(search_history3=self.history3, source="use", selected_query=query)

        elif self.current_key == "history4":
            self.history4 = move_to_top(self.history4, query)
            if self.search_var4: self.search_var4.set(query)
            if self.search_combo4:
                vals = [r["query"] for r in self.history4]
                self.search_combo4["values"] = vals
            if callable(self.sync_history_callback):
                self.sync_history_callback(search_history4=self.history4, source="use", selected_query=query)
        
        elif self.current_key == "history5":
            self.history5 = move_to_top(self.history5, query)
            if self.search_var5: self.search_var5.set(query)
            if self.search_combo5:
                vals = [r["query"] for r in self.history5]
                self.search_combo5["values"] = vals
            if callable(self.sync_history_callback):
                self.sync_history_callback(search_history5=self.history5, source="use", selected_query=query)
        
        self.refresh_tree()
        # self.save_search_history() # 不再不停自动保存，由用户应用过滤器或关闭时保存

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
        elif history_key == "history4": combo, var, target = self.search_combo4, self.search_var4, self.history4
        elif history_key == "history5": combo, var, target = self.search_combo5, self.search_var5, self.history5
        else: return
        if action == "delete":
            target[:] = [r for r in target if r.get("query") != query]
            if combo: combo['values'] = [r.get("query") for r in target]
            if var and var.get() == query: var.set("")
        elif action == "add":
            # 先删除相同 query 的记录，然后插入到第 0 位（实现置顶）
            target[:] = [r for r in target if r.get("query") != query]
            target.insert(0, record.copy())
            if combo: combo['values'] = [r.get("query") for r in target]
        if callable(self.sync_history_callback):
            if self.root and hasattr(self.root, "_suppress_sync") and getattr(self.root, "_suppress_sync"): return
            try:
                cb_kwargs = {"source": action if action == "add" else "sync", "selected_query": query}
                if history_key == "history1": self.sync_history_callback(search_history1=self.history1, **cb_kwargs)
                elif history_key == "history2": self.sync_history_callback(search_history2=self.history2, **cb_kwargs)
                elif history_key == "history3": self.sync_history_callback(search_history3=self.history3, **cb_kwargs)
                elif history_key == "history4": self.sync_history_callback(search_history4=self.history4, **cb_kwargs)
                elif history_key == "history5": self.sync_history_callback(search_history5=self.history5, **cb_kwargs)
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
        self._history_changed = True  # 标记已修改
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
        elif history_key == "history4": target_history = self.history4
        elif history_key == "history5": target_history = self.history5
        else: return
        if any(r.get("query") == record.get("query") for r in target_history):
            toast_message(self.root, f"已存在：{record.get('query')}", 1200)
            return
        if 0 <= index <= len(target_history): target_history.insert(index, record)
        else: target_history.insert(0, record)
        self._history_changed = True  # 标记已修改（撤销恢复也算变更）
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
        if callable(self.test_callback):
            self.test_callback(onclick=True)
        else:
            self.on_test_code(onclick=True)

    def on_test_code(self, onclick=False):
        code = self.entry_query.get().strip()
        result = getattr(self, "_Categoryresult", "")

        if code and code == result:
            df_code = self.df_all
        elif code and not (code.isdigit() and len(code) == 6):
            df_code = self.df_all
        elif code and code.isdigit() and len(code) == 6:
            # [FIX] 如果 df_all 为空，尝试自动注入测试数据
            if self.df_all is None:
                try:
                    toast_message(self.root, "正在通过 test_single 自动注入测试基准数据...", 2000)
                    from instock_MonitorTK import test_single_thread
                    self.df_all = test_single_thread(single=True)
                    logger.info(f"✅ 自动注入测试数据成功，共 {len(self.df_all) if self.df_all is not None else 0} 条")
                except Exception as e:
                    logger.error(f"❌ 自动注入数据失败: {e}")

            if not hasattr(self, "_select_on_test_code"):
                self._select_on_test_code = None

            if self._select_on_test_code != code:
                self._select_on_test_code = code
                if self.df_all is not None:
                    df_code = self.df_all.loc[self.df_all.index == code]
                    from stock_logic_utils import check_code
                    results = check_code(self.df_all, code, self.search_var1.get() if self.search_var1 else "")
                else:
                    df_code = None
            else:
                if onclick:
                    if self.df_all is not None:
                        df_code = self.df_all.loc[self.df_all.index == code]
                        from stock_logic_utils import check_code
                        results = check_code(self.df_all, code, self.search_var1.get() if self.search_var1 else "")
                        logger.info(f'check_code: {results}')
                        # 更新状态栏
                        self.update_status(rows_hit=1 if results else 0, rows_all=len(self.df_all), query=self.search_var1.get() if self.search_var1 else "")
                    else:
                        df_code = None

                    if hasattr(self, "tree_scroll_to_code"):
                        self.tree_scroll_to_code(code)
                    if hasattr(self, "kline_monitor") and self.kline_monitor and getattr(self.kline_monitor, "winfo_exists", lambda: False)():
                        self.kline_monitor.tree_scroll_to_code_kline(code)
                else:
                    df_code = self.df_all
        else:
            # [FIX] 全部测试模式下的数据补齐逻辑
            if self.df_all is None:
                try:
                    from instock_MonitorTK import test_single_thread
                    self.df_all = test_single_thread(single=True)
                except: pass
            df_code = self.df_all

        if df_code is not None:
            results = self.test_code(df_code)
            
            # [NEW] 优化状态栏展示逻辑：区分单条测试与批量回测
            input_query = self.entry_query.get().strip()
            total_stocks = len(df_code)
            if not input_query:
                # 批量模式：展示列表汇总
                queries_count = len(self.current_history)
                self.status_var.set(f"📊 批量回测完成 | 列表:{queries_count} 条 | 样本:{total_stocks} 只")
                self.status_var2.set("所有历史已同步")
            else:
                # 单条模式：展示该查询的具体命中
                # 寻找 results 中第一个匹配 input_query 的命中数（如果存在）
                hit_count = sum(1 for r in results if r.get("hit") and str(r.get("hit")) != "0")
                self.update_status(rows_hit=hit_count, rows_all=total_stocks, query=input_query)

            for i, r in enumerate(results):
                if i < len(self.current_history):
                    self.current_history[i]["hit"] = r.get("hit", "")

            self.refresh_tree()

    def test_code(self, code_data):
        queries = getattr(self, "current_history", [])
        return test_code_against_queries(code_data, queries)



    def on_tree_select(self, event):
        """[NEW] 增强联动：点击表格行时，状态栏同步显示该行的命中信息"""
        try:
            selected = self.tree.selection()
            if not selected: return
            vals = self.tree.item(selected[0], "values")
            if not vals: return
            
            q_text = str(vals[0])
            hit_str = str(vals[3]) if len(vals) > 3 else "0"
            try:
                hit_val = int(hit_str)
            except:
                hit_val = 0
                
            rows_all = len(self.df_all) if self.df_all is not None else 0
            self.update_status(rows_hit=hit_val, rows_all=rows_all, query=q_text)
        except Exception as e:
            logger.debug(f"on_tree_select error: {e}")

    def update_status(self, rows_hit=0, rows_all=0, query=""):
        """同步展示状态栏信息，支持预处理清洗后的 Q 展示"""
        try:
            from query_engine_util import query_engine
            # 对查询语句进行脱敏预处理 (剥离注释、赋值等)
            eff_query = query_engine._preprocess_query(query) if query_engine else query
            disp_query = eff_query[:120].replace('\n', ' ').strip()
        except Exception:
            disp_query = query[:120].strip()
            
        self.status_var.set(f"✨ 匹配:{rows_hit}/{rows_all} | Q:{disp_query}...")
        self.status_var2.set("")


def quick_save_specific_history(query, history_key="history5", note=""):
    """
    [NEW] 快速保存一个查询到指定历史分组，不经过 QueryHistoryManager 实例。
    主要用于 Visualizer 等其他模块静默保存筛选成功的条件。
    """
    if not query: return
    
    from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
    history_file = SEARCH_HISTORY_FILE
    
    data = {"history1":[], "history2":[], "history3":[], "history4":[], "history5":[]}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"[quick_save_specific_history] Load error: {e}")
            
    # 获取目标列表
    target_list = data.get(history_key, [])
    if not isinstance(target_list, list): target_list = []
    
    # 归一化处理 (参考 QueryHistoryManager._normalize_record)
    new_record = {"query": str(query).strip(), "starred": 0, "note": str(note).strip()}
    
    # 去重逻辑：如果已经存在相同 query，则移到最前，或者不处理。
    # 这里采用“移到最前”逻辑，保持活性。
    new_list = []
    new_list.append(new_record)
    
    seen_queries = {new_record["query"]}
    for item in target_list:
        if not isinstance(item, dict):
            q_val = str(item).strip()
        else:
            q_val = item.get("query", "").strip()
            
        if q_val and q_val not in seen_queries:
            if isinstance(item, dict):
                new_list.append(item)
            else:
                new_list.append({"query": q_val, "starred": 0, "note": ""})
            seen_queries.add(q_val)
            
    # 限制长度
    data[history_key] = new_list[:100]
    
    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[quick_save_specific_history] Query saved to {history_key}: {query}")
        return True
    except Exception as e:
        logger.error(f"[quick_save_specific_history] Save error: {e}")
        return False

def run_manager_process(history_path=None, df_all=None):
    """
    独立进程入口点，用于启动历史查询管理器
    """
    # Import config at runtime to avoid circular dependencies
    try:
        from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
        if history_path is None:
            history_path = SEARCH_HISTORY_FILE
    except ImportError:
        # Fallback if config module not found
        if history_path is None:
            history_path = "query_history.json"
    
    # [FIX] High DPI Awareness for Windows EXEs
    try:
        import ctypes
        import platform
        if platform.system() == "Windows":
            # 尝试 SetProcessDpiAwareness(1) -> PROCESS_SYSTEM_DPI_AWARE
            # 避免使用 2 (Per-Monitor), Tkinter 对 Per-Monitor 支持一般
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            # Fallback for older Windows
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    root = tk.Tk()
    root.title("Query History Manager")
    
    # [FIX] Manually adjust scaling based on DPI
    scale_factor = 1.0
    try:
        # Standard DPI is 96. Get actual DPI based on screen scaling.
        dpi = root.winfo_fpixels('1i')
        scale_factor = dpi / 96.0
        
        # If scale factor is < 1, dont shrink it. If > 1, scale up.
        if scale_factor < 1.0: scale_factor = 1.0
        
        # Correctly inform Tkinter about the screen resolution (Points to Pixels)
        # 1 Point = 1/72 inch. Tkinter needs pixels per point.
        # This fixes font sizes and widget padding automatically without manual font.configure
        root.tk.call('tk', 'scaling', dpi / 72.0)
        
    except Exception:
        scale_factor = 1.0

    print(f"DPI: {dpi if 'dpi' in locals() else 'Unknown'} | Geometry Scale Factor: {scale_factor}")

    # Calculate window size and position
    # Window geometry needs physical pixels when DPI Aware is ON
    w, h = int(900 * scale_factor), int(650 * scale_factor) 
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)
    root.geometry('%dx%d+%d+%d' % (w, h, x, y))
    
    # Remove manual font configuration as 'tk scaling' handles it now
    # This prevents double-scaling issues (huge fonts)

    # [FIX] Manually adjust Treeview row height
    # Tkinter's automatic scaling sometimes misses the row height, causing overlap.
    try:
        import tkinter.ttk as ttk
        style = ttk.Style()
        # Base row height 25, scaled by DPI factor
        style.configure("Treeview", rowheight=int(30 * scale_factor))
        style.configure("Treeview.Heading", font=('Segoe UI', 10)) # Optional: ensure heading is readable
    except Exception as e:
        print(f"Style config error: {e}")

    # Create manager with auto_run=True to show editor immediately
    manager = QueryHistoryManager(
        root=root, 
        auto_run=True,
        history_file=history_path,
        df_all=df_all
    )
    
    # Debug: Print loaded history count
    print(f"Loaded history counts: H1={len(manager.history1)}, H2={len(manager.history2)}, H3={len(manager.history3)}, H4={len(manager.history5)},H5={len(manager.history5)}")
    print(f"History file path: {history_path}")
    print(f"File exists: {os.path.exists(history_path)}")
    
    root.mainloop()

if __name__ == "__main__":
    # [NEW] 支持通过 -test 参数直接注入测试数据
    import sys
    df_all_inject = None
    if "-test" in sys.argv:
        try:
            print("🚀 正在通过 test_single_thread 注入测试数据...")
            from instock_MonitorTK import test_single_thread
            df_all_inject = test_single_thread(single=True)
            print(f"✅ 数据注入完成: {len(df_all_inject) if df_all_inject is not None else 0} 条")
        except Exception as e:
            print(f"❌ 数据注入失败: {e}")
            
    run_manager_process(df_all=df_all_inject)
