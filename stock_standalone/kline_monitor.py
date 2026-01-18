# -*- coding:utf-8 -*-
import tkinter as tk
from tkinter import ttk
import threading
import time
import re
import traceback
import numpy as np
import pandas as pd
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import pyperclip
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct
from gui_utils import askstring_at_parent_single
from stock_logic_utils import detect_signals, get_row_tags, ensure_parentheses_balanced
from history_manager import toast_message

# 获取或创建日志记录器
logger = LoggerFactory.getLogger("instock_TK.KLineMonitor")

class KLineMonitor(tk.Toplevel):
    def __init__(self, parent: tk.Widget, get_df_func: Callable[[], Optional[pd.DataFrame]], refresh_interval: int = 30, history3: Optional[Callable[[], List[str]]] = None ,logger=logger) -> None :
        super().__init__(parent)
        self.master = parent
        self.get_df_func = get_df_func
        self.refresh_interval = refresh_interval
        self.stop_event = threading.Event()
        self.sort_column = None
        self.sort_reverse = False
        self.history3 = history3
        # 点击计数器
        self.click_count = 0
        self.search_filter_by_signal = True
        # 历史信号追踪
        self.buy_history_indices = set()
        self.sell_history_indices = set()
        self.signal_types = ["BUY_S", "BUY_N", "SELL"]
        # 筛选栈
        self.filter_stack = []
        self.last_query = ""
        # 缓存数据
        self.df_cache = None

        self.title("K线趋势实时监控")
        self.geometry("760x460")

        # ---- 状态栏 ----
        self.status_frame = tk.Frame(self, bg="#eee")
        self.status_frame.pack(fill="x")

        self.total_label = tk.Label(self.status_frame, text="总数: 0", bg="#eee")
        self.total_label.pack(side="left", padx=5)

        # 动态生成信号统计标签
        self.signal_labels = {}
        for sig in self.signal_types:
            lbl = tk.Label(self.status_frame, text=f"{sig}: 0", bg="#eee", cursor="hand2")
            lbl.pack(side="left", padx=5)
            lbl.bind("<Button-1>", lambda e, s=sig: self.filter_by_signal(s))
            self.signal_labels[sig] = lbl

        # 情绪标签保持不变
        self.emotion_labels = {}
        for emo, color in [("乐观", "green"), ("悲观", "red"), ("中性", "gray")]:
            lbl = tk.Label(self.status_frame, text=f"{emo}: 0", fg=color, cursor="hand2", bg="#eee")
            lbl.pack(side="left", padx=5)
            lbl.bind("<Button-1>", lambda e, em=emo: self.filter_by_emotion(em))
            self.emotion_labels[emo] = lbl

        # 全局显示按钮
        self.global_btn = tk.Button(self.status_frame, text="全局", cursor="hand2", command=self.reset_filters)
        self.global_btn.pack(side="right", padx=5)

        # ---- 表格 + 滚动条 ----
        table_frame = tk.Frame(self)
        table_frame.pack(fill=tk.BOTH, expand=True)

        # 自定义窄滚动条样式
        style = ttk.Style(self)
        style.configure(
            "Thin.Vertical.TScrollbar",
            troughcolor="#f2f2f2",
            background="#c0c0c0",
            bordercolor="#f2f2f2",
            lightcolor="#f2f2f2",
            darkcolor="#f2f2f2",
            arrowsize=10,
            width=8
        )

        self.tree = ttk.Treeview(
            table_frame,
            columns=("code", "name", "now", "percent", "volume", "signal", "Rank", "score", "red", "emotion"),
            show="headings",
            height=20
        )
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
            style="Thin.Vertical.TScrollbar"
        )
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)

        for col, text, w in [
            ("code", "代码", 40),
            ("name", "名称", 60),
            ("now", "当前价", 30),
            ("percent", "涨幅",30),
            ("volume", "量比", 30),
            ("signal", "信号", 60),
            ("Rank", "Rank", 30),
            ("score", "评分", 30),
            ("red", "连阳", 30),
            ("emotion", "情绪", 60)
        ]:
            self.tree.heading(col, text=text, command=lambda c=col: self.treeview_sort_columnKLine(c, onclick=True))
            self.tree.column(col, width=w, anchor="center")

        self.tree.tag_configure("neutral", background="#f0f0f0")
        for sig in self.signal_types:
            self.tree.tag_configure(sig.lower(), background="#d0f0d0")
        self.tree.tag_configure("buy_hist", background="#b0f0b0")
        self.tree.tag_configure("sell_hist", background="#f0b0b0")
        self.tree.tag_configure("red_row", foreground="red")
        self.tree.tag_configure("orange_row", foreground="orange")
        self.tree.tag_configure("green_row", foreground="green")
        self.tree.tag_configure("blue_row", foreground="#555555")
        self.tree.tag_configure("purple_row", foreground="purple")
        self.tree.tag_configure("yellow_row", foreground="yellow")

        self.tree.bind("<Button-1>", self.on_tree_kline_monitor_click)
        self.tree.bind("<Button-3>", self.on_tree_kline_monitor_right_click)
        self.tree.bind("<Double-1>", self.on_tree_kline_monitor_double_click)
        self.tree.bind("<Up>", self.on_key_select)
        self.tree.bind("<Down>", self.on_key_select)

        # ---- 窗口底部状态栏 ----
        self.query_status_var = tk.StringVar(value="")
        self.query_status_label = tk.Label(
            self,
            textvariable=self.query_status_var,
            anchor="w",
            bg="#f0f0f0",
            fg="blue"
        )
        self.query_status_label.pack(side="bottom", fill="x")

        # --- 搜索框区域 ---
        self.search_var = tk.StringVar()
        h3_values = self.history3() if callable(self.history3) else (self.history3 or [])
        self.search_combo3 = ttk.Combobox(self.status_frame, textvariable=self.search_var, values=h3_values, width=20)
        self.search_combo3.pack(side="left", padx=5, fill="x", expand=True)
        self.search_combo3.bind("<Return>", lambda e: self.search_code_status(onclick=True))
        self.search_combo3.bind("<Button-3>", self.on_kline_monitor_right_click)
        self.search_combo3.bind("<<ComboboxSelected>>", lambda e: self.search_code_status(onclick=True))

        self.search_btn = tk.Button(
            self.status_frame, text="查询", cursor="hand2", command=lambda: self.search_code_status(onclick=True)
        )
        self.search_btn.pack(side="left", padx=3)

        self.search_btn2 = tk.Button(
            self.status_frame, text="编辑", cursor="hand2", command=self.edit_code_status)
        self.search_btn2.pack(side="left", padx=3)

        if h3_values:
            self.search_var.set(h3_values[0])

        self.refresh_thread = threading.Thread(target=self.refresh_loop, daemon=True)
        self.refresh_thread.start()
        self.protocol("WM_DELETE_WINDOW", self.on_kline_monitor_close)
       
        try:
            self.master.load_window_position(self, "KLineMonitor", default_width=860, default_height=560)
        except Exception:
            self.geometry("760x460")

    def refresh_search_combo3(self) -> None:
        if hasattr(self, "search_combo3") and self.search_combo3.winfo_exists():
            try:
                values = self.history3() if callable(self.history3) else self.history3
                values = list(values) if values else []
                self.search_combo3["values"] = values
                if values:
                    self.search_var.set(values[0])
                else:
                    self.search_var.set("")
            except Exception as e:
                logger.info(f"[refresh_search_combo3] 刷新失败: {e}")

    def edit_code_status(self) -> None:
        h3 = self.history3() if callable(self.history3) else self.history3
        query = h3[0] if h3 else ""
        new_note = askstring_at_parent_single(self, "修改备注", "请输入新的备注：", initialvalue=query)
        if new_note is not None:
            self.search_var.set(new_note)
            if h3:
                h3[0] = new_note
            self.search_combo3["values"] = h3
            self.search_combo3.set(new_note)
            self.search_code_status()

    def search_code_status(self, onclick: bool = False) -> None:
        query = self.search_var.get().strip()
        if onclick:
            self.search_filter_by_signal = True
        if not self.search_filter_by_signal or not query:
            return

        self.last_query = query

        if query.isdigit() and len(query) == 6:
            code = query
            found = False
            for item in self.tree.get_children():
                if self.tree.set(item, "code") == code:
                    self.tree.selection_set(item)
                    self.tree.focus(item)
                    self.tree.see(item)
                    found = True
                    break
            if not found:
                toast_message(self, f"未找到代码 {code}")
            else:
                try:
                    self.lift()
                    self.focus_force()
                except Exception:
                    pass
            return

        try:
            df_filtered = self.apply_filters()
            toast_message(self, f"共找到 {len(df_filtered)} 条结果")
            try:
                self.lift()
                self.focus_force()
            except Exception:
                pass
        except Exception as e:
            toast_message(self, f"筛选语句错误: {e}")

    def tree_scroll_to_code_kline(self, code: str) -> bool:
        if not code or not (code.isdigit() and len(code) == 6):
            return False
        try:
            for iid in self.tree.get_children():
                values = self.tree.item(iid, "values")
                if values and str(values[0]) == str(code):
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    return True
            toast_message(self.master, f"{code} is not Found in kline")
        except Exception as e:
            logger.info(f"[tree_scroll_to_code] Error: {e}")
            return False
        return False

    def on_kline_monitor_right_click(self, event):
        try:
            clipboard_text = event.widget.clipboard_get()
        except tk.TclError:
            return
        event.widget.delete(0, tk.END)
        event.widget.insert(0, clipboard_text)
        self.search_code_status()

    def on_tree_kline_monitor_click(self, event=None, item_id=None):
        try:
            if item_id is None and event is not None:
                item_id = self.tree.identify_row(event.y)
            if not item_id:
                return

            self.tree.selection_set(item_id)
            self.tree.focus(item_id)

            values = self.tree.item(item_id, "values")
            stock_code = values[0] if len(values) > 0 else None

            self.click_count += 1
            if self.click_count % 10 == 0:
                logger.info(f"[Monitor] 点击了 {stock_code}")

            if hasattr(self.master, "on_single_click"):
                send_tdx_Key = (getattr(self.master, "select_code", None) != stock_code)
                self.master.select_code = stock_code
                stock_code = str(stock_code).zfill(6)
                if send_tdx_Key and stock_code:
                    self.master.sender.send(stock_code)
                    
                # ⭐ 可视化器联动
                if hasattr(self.master, 'vis_var') and self.master.vis_var.get():
                    if hasattr(self.master, 'open_visualizer'):
                         self.master.open_visualizer(str(stock_code))
        except Exception as e:
            logger.info(f"[Monitor] 点击处理错误: {e}")

    def on_tree_kline_monitor_double_click(self, event=None, item_id=None):
        try:
            if item_id is None and event is not None:
                item_id = self.tree.identify_row(event.y)
            if not item_id:
                return

            self.tree.selection_set(item_id)
            self.tree.focus(item_id)

            values = self.tree.item(item_id, "values")
            stock_code = values[0] if len(values) > 0 else None
            stock_code = str(stock_code).zfill(6)
            query_str = f'index.str.contains("^{stock_code}")'
            pyperclip.copy(query_str)
            if hasattr(self.master, "plot_following_concepts_pg"):
                self.master.plot_following_concepts_pg(stock_code, top_n=1)
        except Exception as e:
            logger.info(f"[Monitor] double_click错误:{e}")
            traceback.print_exc()

    def on_tree_kline_monitor_right_click(self, event=None, item_id=None):
        try:
            if item_id is None and event is not None:
                item_id = self.tree.identify_row(event.y)
            if not item_id:
                return

            self.tree.selection_set(item_id)
            self.tree.focus(item_id)

            values = self.tree.item(item_id, "values")
            stock_code = values[0] if len(values) > 0 else None
            stock_code = str(stock_code).zfill(6)

            if hasattr(self.master, "push_stock_info"):
                if self.master.push_stock_info(stock_code, self.master.df_all.loc[stock_code]):
                    self.master.status_var2.set(f"发送成功: {stock_code}")
                else:
                    self.master.status_var2.set(f"发送失败: {stock_code}")
        except Exception as e:
            logger.info(f"[Monitor] 点击处理错误: {e}")

    def on_key_select(self, event):
        try:
            children = self.tree.get_children()
            if not children:
                return "break"
            sel_items = self.tree.selection()
            if not sel_items:
                item_id = children[0]
            else:
                current_index = children.index(sel_items[0])
                if event.keysym == "Up":
                    item_id = children[max(0, current_index - 1)]
                elif event.keysym == "Down":
                    item_id = children[min(len(children) - 1, current_index + 1)]
                else:
                    return "break"
            self.tree.see(item_id)
            self.on_tree_kline_monitor_click(item_id=item_id)
        except Exception as e:
            logger.info(f"[Monitor] 键盘选择错误:{e}")
        return "break"

    def treeview_sort_columnKLine(self, col: str, reverse: bool = False, onclick: bool = False) -> None:
        try:
            y = self.tree.yview()
            self.sort_column = col
            self.sort_reverse = reverse
            data_list = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
            try:
                data_list.sort(key=lambda t: float(t[0]), reverse=reverse)
            except ValueError:
                data_list.sort(reverse=reverse)
            for index, (val, k) in enumerate(data_list):
                self.tree.move(k, '', index)
            self.tree.heading(col, command=lambda: self.treeview_sort_columnKLine(col, not reverse, onclick=True))
            if onclick:
                self.tree.yview_moveto(0)
            else:
                self.tree.yview_moveto(y[0])
        except Exception as e:
            logger.info(f"[Monitor] 排序错误:{e}")

    def refresh_loop(self):
        try:
            df = self.get_df_func()
            if df is not None and not df.empty:
                self.df_cache = df.copy()
                self.after(0, self.apply_filters)
        except Exception as e:
            logger.info(f"[Monitor] 初次更新错误:{e}")

        while not self.stop_event.is_set():
            try:
                if cct.get_work_time():
                    df = self.get_df_func()
                    if df is not None and not df.empty:
                        df = detect_signals(df)
                        self.df_cache = df.copy()
                        self.after(0, self.apply_filters)
                else:
                    time.sleep(10)
                if not self.stop_event.is_set():
                    time.sleep(self.refresh_interval)
            except Exception as e:
                logger.error(f"[Monitor] 更新错误: {e}")
                time.sleep(self.refresh_interval)

    def get_row_tags_kline(self, r: pd.Series, idx: Optional[Any] = None) -> List[str]:
        tags = []
        sig = str(r.get("signal", "") or "")
        if sig.startswith("BUY"):
            tags.append("buy")
        elif sig.startswith("SELL"):
            tags.append("sell")
        else:
            tags.append("neutral")

        if idx is not None:
            if hasattr(self, "signal_history_indices"):
                for s in self.signal_types:
                    if idx in self.signal_history_indices.get(s, set()):
                        tags.append(f"{tags[0]}_hist")

        row_tags = get_row_tags(r)
        tags.extend(row_tags) 
        return tags

    def process_table_data(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        processed = []
        if not hasattr(self, "cumulative_signals"):
            self.cumulative_signals = {}
        if not hasattr(self, "price_history"):
            self.price_history = {}
            self.max_history_len = 10
        if not hasattr(self, "signal_history_indices"):
            self.signal_history_indices = {sig: set() for sig in self.signal_types}
            self.last_signal_index = {sig: None for sig in self.signal_types}

        for idx, r in df.iterrows():
            code = r.get("code")
            sig = str(r.get("signal", "") or "")
            now_price = r.get("now", 0)

            if code not in self.price_history:
                self.price_history[code] = deque(maxlen=self.max_history_len)
            self.price_history[code].append(now_price)

            ph = np.array(self.price_history[code])
            trend = "flat"

            if len(ph) >= 3:
                x = np.arange(len(ph))
                y = ph
                A = np.vstack([x, np.ones(len(x))]).T
                slope, _ = np.linalg.lstsq(A, y, rcond=None)[0]
                if slope > 0.01:
                    trend = "up"
                elif slope < -0.01:
                    trend = "down"
                else:
                    trend = "flat"

            if code not in self.cumulative_signals:
                self.cumulative_signals[code] = []

            if sig in self.signal_types:
                if trend == "up":
                    self.cumulative_signals[code].append(sig)
                elif trend == "down" and self.cumulative_signals[code]:
                    try:
                        self.cumulative_signals[code].remove(sig)
                    except ValueError:
                        pass
                self.signal_history_indices[sig].add(idx)
                self.last_signal_index[sig] = idx

            count = self.cumulative_signals.get(code, []).count(sig) if sig else 0
            arrow = "↑" if trend=="up" else ("↓" if trend=="down" else "→")
            display_signal = f"{sig} {arrow}{count}" if sig else ""

            tag = self.get_row_tags_kline(r, idx=idx)
            processed.append({
                "code": code,
                "name": r.get("name",""),
                "now": now_price,
                "percent": r.get("percent",0) or r.get("per1d",0),
                "volume": r.get("volume",0),
                "display_signal": display_signal,
                "Rank": r.get("Rank", 0),
                "score": r.get("score",0),
                "red": r.get("red",0),
                "emotion": r.get("emotion",""),
                "tag": tag
            })
        return processed

    def update_table(self, df: pd.DataFrame) -> None:
        selected_code = None
        sel_items = self.tree.selection()
        if sel_items:
            values = self.tree.item(sel_items[0], "values")
            if values:
                selected_code = values[0]

        processed_data = self.process_table_data(df)
        self.tree.delete(*self.tree.get_children())

        for row in processed_data:
            self.tree.insert(
                "", tk.END,
                values=(
                    row["code"],
                    row["name"],
                    f"{row['now']:.2f}",
                    f"{row['percent']:.2f}",
                    f"{row['volume']:.1f}",
                    row["display_signal"],
                    f"{row['Rank']}",
                    f"{row['score']}",
                    f"{row['red']}",
                    row["emotion"]
                ),
                tags=tuple(row["tag"]) 
            )

        if getattr(self, "sort_column", None):
            self.treeview_sort_columnKLine(self.sort_column, self.sort_reverse)

        if selected_code:
            for item in self.tree.get_children():
                if self.tree.set(item, "code") == selected_code:
                    self.tree.selection_set(item)
                    self.tree.focus(item)
                    self.tree.see(item)
                    break

        total = len(df)
        self.total_label.config(text=f"总数: {total}")
        signal_counts = df["signal"].value_counts().to_dict()
        for sig, lbl in self.signal_labels.items():
            count = signal_counts.get(sig, 0)
            lbl.config(text=f"{sig}: {count}")

        emotion_counts = df["emotion"].value_counts().to_dict()
        for emo, lbl in self.emotion_labels.items():
            lbl.config(text=f"{emo}: {emotion_counts.get(emo, 0)}")

        self.query_status_var.set(f"共找到 {len(df)} 条结果")

    def filter_by_signal(self, signal):
        self.filter_stack.append({"type":"signal","value":signal})
        self.apply_filters()

    def filter_by_emotion(self, emotion):
        self.filter_stack.append({"type":"emotion","value":emotion})
        self.apply_filters()

    def reset_filters(self):
        self.filter_stack.clear()
        self.search_filter_by_signal = False
        if self.df_cache is not None:
            self.update_table(self.df_cache)

    def apply_filters(self):
        if not self.search_filter_by_signal or self.df_cache is None or self.df_cache.empty:
            return None

        df = self.df_cache.copy()
        for f in getattr(self, "filter_stack", []):
            if f["type"] == "signal":
                df = df[df["signal"] == f["value"]]
            elif f["type"] == "emotion":
                df = df[df["emotion"] == f["value"]]

        query_text = ""
        if hasattr(self, "search_var") and self.search_var.get().strip():
            query_text = self.search_var.get().strip()
        elif hasattr(self, "last_query") and self.last_query:
            query_text = self.last_query.strip()

        if query_text:
            try:
                query = query_text
                if query.count('or') > 0 and query.count('(') > 0:
                    query_search = f"({query})"
                    query_engine = 'python' if any('index.' in c.lower() for c in query) or ('.str' in query and '|' in query) else 'numexpr'
                    df = df.query(query_search, engine=query_engine)
                else:
                    bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)
                    for bracket in bracket_patterns:
                        query = query.replace(f'and {bracket}', '')
                    conditions = [c.strip() for c in query.split('and')]
                    valid_conditions = []
                    removed_conditions = []
                    for cond in conditions:
                        cond_clean = cond.lstrip('(').rstrip(')')
                        if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower() or '==' in cond or 'or' in cond:
                            if not any(bp.strip('() ').strip() == cond_clean for bp in bracket_patterns):
                                valid_conditions.append(ensure_parentheses_balanced(cond))
                                continue
                        cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)
                        if all(col in df.columns for col in cols_in_cond):
                            valid_conditions.append(cond_clean)
                        else:
                            removed_conditions.append(cond_clean)

                    if not valid_conditions:
                        return df

                    final_query = ' and '.join(f"({c})" for c in valid_conditions)
                    if bracket_patterns:
                        final_query += ' and ' + ' and '.join(bracket_patterns)
                    
                    final_query = ensure_parentheses_balanced(final_query)
                    query_engine = 'python' if any('index.' in c.lower() for c in valid_conditions) else 'numexpr'

                    for col in ["score", "percent", "volume", "now", "Rank"]:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")

                    if query_text.isdigit() and len(query_text) == 6:
                        df = df[df["code"] == query_text]
                    else:
                        df = df.query(final_query, engine=query_engine)

            except Exception as e:
                logger.info(f"[apply_filters] 查询错误: {e}")

        self.update_table(df)
        return df

    def on_kline_monitor_close(self):
        self.stop()
        try:
            self.master.save_window_position(self, "KLineMonitor")
        except Exception:
            pass

        if getattr(self, "df_cache", None) is None or len(getattr(self.df_cache, "index", [])) == 0:
            logger.info("[KLineMonitor] 无数据，销毁窗口。")
            try:
                self.destroy()
            except Exception:
                pass
            if hasattr(self.master, "kline_monitor"):
                self.master.kline_monitor = None
        else:
            logger.info("[KLineMonitor] 有数据，隐藏窗口。")
            try:
                self.withdraw()
            except Exception:
                pass
    def stop(self):
        """信号停止线程并等待结束"""
        self.stop_event.set()
        if hasattr(self, "refresh_thread") and self.refresh_thread.is_alive():
            try:
                # 尽量等待其退出，避免 GIL 冲突
                self.refresh_thread.join(timeout=0.5)
            except Exception:
                pass
