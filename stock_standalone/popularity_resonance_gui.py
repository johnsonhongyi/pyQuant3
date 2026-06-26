# -*- encoding: utf-8 -*-
"""
人气共振数据同步工具 GUI 客户端 - 高仿真版
代替旧版易语言客户端，支持配置抓取源、自定义通达信路径、定时自动刷新等功能。
集成物理通道联动 (TDX/Ths 及可视化终端)，支持窄边框模式，无数据板块自动隐藏。
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import socket

# 导入核心逻辑
try:
    from popularity_resonance_service import (
        fetch_eastmoney,
        fetch_ths,
        fetch_taoguba,
        fetch_longhu,
        calculate_resonance_scores,
        write_to_tdx_blocks,
        fetch_realtime_quotes,
        logger as service_logger
    )
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from popularity_resonance_service import (
        fetch_eastmoney,
        fetch_ths,
        fetch_taoguba,
        fetch_longhu,
        calculate_resonance_scores,
        write_to_tdx_blocks,
        fetch_realtime_quotes,
        logger as service_logger
    )

import traceback

def _log_import_error(name):
    try:
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base_dir, "linkage_err.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"--- IMPORT ERROR FOR {name} AT {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except:
        pass

try:
    from linkage_service import get_link_manager
except Exception:
    _log_import_error("linkage_service")
    get_link_manager = None

try:
    from JohnsonUtil.stock_sender import StockSender
except Exception:
    _log_import_error("StockSender")
    StockSender = None

def get_app_root():
    """获取程序运行根目录，兼容打包环境"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except NameError:
            return os.path.dirname(os.path.abspath(sys.argv[0]))

CONFIG_FILE = os.path.join(get_app_root(), "popularity_resonance_config.json")

class PRServiceGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("人气综合排行榜2.22")
        
        # 加载配置（必须在设置 geometry 前加载）
        self.config = self.load_config_settings()
        
        # 恢复窗口位置与大小，默认 620x760
        saved_geo = self.config.get("geometry", "620x760")
        try:
            self.root.geometry(saved_geo)
        except Exception:
            self.root.geometry("620x760")
        
        self.is_running = False
        self.refresh_thread = None
        self.resonance_codes = []  # 缓存当前的共振股票代码
        
        # 联动选择项变量
        self.link_tdx_var = tk.BooleanVar(value=self.config.get("link_tdx", True))
        self.link_ths_var = tk.BooleanVar(value=self.config.get("link_ths", True))
        self.link_vis_var = tk.BooleanVar(value=self.config.get("link_vis", True))
        
        # 初始化本地 StockSender 作为 fallback
        if StockSender:
            try:
                self.local_sender = StockSender(tdx_var=self.link_tdx_var, ths_var=self.link_ths_var, dfcf_var=False)
            except Exception:
                self.local_sender = None
        else:
            self.local_sender = None
            
        self.create_widgets()

        
        # 初始化布局 (全部为空，所以先隐藏)
        self.refresh_layout(em_empty=True, ths_empty=True, lh_empty=True, res_empty=True, tgb_empty=True)

        # 尝试加载缓存数据并恢复表格
        self.load_cached_data()

        # 监听窗口关闭事件，确保最终配置得到持久化保存
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.save_config_settings()
        self.root.destroy()


    def load_config_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {
            "blk_name": "RQG.blk",
            "limit": 50,
            "interval": 5,
            "link_tdx": True,
            "link_ths": True,
            "link_vis": True,
            "sort_col": None,
            "sort_descending": False
        }
        
    def save_config_settings(self):
        try:
            self.config["blk_name"] = self.entry_blk_name.get().strip() or "RQG.blk"
            self.config["limit"] = int(self.entry_limit.get() or "50")
            self.config["interval"] = float(self.entry_interval.get() or "5")
            self.config["link_tdx"] = self.link_tdx_var.get()
            self.config["link_ths"] = self.link_ths_var.get()
            self.config["link_vis"] = self.link_vis_var.get()
            
            # 保存窗口位置与大小
            try:
                self.config["geometry"] = self.root.winfo_geometry()
            except Exception:
                pass
            
            # 保存排序状态
            if hasattr(self, "tree_res") and self.tree_res is not None:
                self.config["sort_col"] = self.tree_res.sort_col
                self.config["sort_descending"] = self.tree_res.sort_descending
                
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except:
            pass

    def load_cached_data(self):
        cache_file = os.path.join(get_app_root(), "popularity_resonance_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                em_data = cache.get("em_data", {})
                ths_data = cache.get("ths_data", {})
                tgb_data = cache.get("tgb_data", {})
                lh_data = cache.get("lh_data", {})
                resonance_results = cache.get("resonance_results", [])
                quotes = cache.get("quotes", {})
                
                # 恢复缓存的共振代码
                self.resonance_codes = [r['code'] for r in resonance_results]
                
                # 更新表格，主线程安全
                self.update_all_tables(em_data, ths_data, lh_data, tgb_data, resonance_results, quotes)
                self.lbl_status.config(text="自动加载缓存数据完成", fg="darkgreen")
            except Exception as e:
                self.lbl_status.config(text=f"加载缓存失败: {e}", fg="red")

    def create_widgets(self):
        # 全局样式配置 - clam主题 + 极窄滚动条 + 扁平风格
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei", 9))
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 9, "bold"))
        style.configure("Treeview", rowheight=18, font=("Microsoft YaHei", 9),
                        background="white", fieldbackground="white", borderwidth=0)
        # 极窄滚动条（6px，无箭头）
        style.configure("Slim.Vertical.TScrollbar",
                        gripcount=0,
                        background="#BBBBBB",
                        darkcolor="#999999",
                        lightcolor="#CCCCCC",
                        troughcolor="#F0F0F0",
                        bordercolor="#F0F0F0",
                        arrowsize=0,
                        width=6)
        style.layout("Slim.Vertical.TScrollbar",
                     [("Vertical.Scrollbar.trough",
                       {"sticky": "ns",
                        "children": [("Vertical.Scrollbar.thumb",
                                      {"expand": "1", "sticky": "nswe"})]})])
        
        # 主显示区域 (左右分栏)
        main_pane = tk.Frame(self.root)
        main_pane.pack(fill="both", expand=True, padx=4, pady=2)

        # 左分栏
        self.left_frame = tk.Frame(main_pane)
        self.left_frame.pack(side="left", fill="both", expand=True, padx=2)

        # 查询刷新按钮
        self.btn_refresh = tk.Button(
            self.left_frame,
            text="查询刷新",
            font=("Microsoft YaHei", 12, "bold", "underline"),
            fg="#E02020",
            activeforeground="#A01010",
            bg=self.root.cget('bg'),
            relief="flat",
            cursor="hand2",
            command=self.run_once_async
        )
        self.btn_refresh.pack(pady=4)

        # 东 (EastMoney) Table Frame (1px 窄边框模式)
        self.em_container = tk.Frame(self.left_frame, bg="white", highlightbackground="#CCCCCC", highlightthickness=1, bd=0)
        self.tree_em = self.create_treeview(self.em_container, "东")

        # 左侧横向分隔栏
        self.left_sep = ttk.Separator(self.left_frame, orient="horizontal")

        # 花 (Ths) Table Frame (1px 窄边框模式)
        self.ths_container = tk.Frame(self.left_frame, bg="white", highlightbackground="#CCCCCC", highlightthickness=1, bd=0)
        self.tree_ths = self.create_treeview(self.ths_container, "花")

        # 垂直分隔栏
        self.v_sep = ttk.Separator(main_pane, orient="vertical")
        self.v_sep.pack(side="left", fill="y", padx=6)

        # 右分栏
        self.right_frame = tk.Frame(main_pane)
        self.right_frame.pack(side="left", fill="both", expand=True, padx=2)

        # 写入板块按钮
        self.btn_write = tk.Button(
            self.right_frame,
            text="写入板块",
            font=("Microsoft YaHei", 12, "bold", "underline"),
            fg="#E02020",
            activeforeground="#A01010",
            bg=self.root.cget('bg'),
            relief="flat",
            cursor="hand2",
            command=self.write_block_async
        )
        self.btn_write.pack(pady=4)

        # 开 (LongHu) Table Frame (1px 窄边框模式)
        self.lh_container = tk.Frame(self.right_frame, bg="white", highlightbackground="#CCCCCC", highlightthickness=1, bd=0)
        self.tree_lh = self.create_treeview(self.lh_container, "开")

        # 右侧横向分隔栏1
        self.right_sep1 = ttk.Separator(self.right_frame, orient="horizontal")

        # 合 (Combined) Table Frame (1px 窄边框模式)
        self.res_container = tk.Frame(self.right_frame, bg="white", highlightbackground="#CCCCCC", highlightthickness=1, bd=0)
        self.tree_res = self.create_treeview(self.res_container, "合")

        # 右侧横向分隔栏2
        self.right_sep2 = ttk.Separator(self.right_frame, orient="horizontal")

        # 淘 (TaoGuBa) Table Frame (1px 窄边框模式)
        self.tgb_container = tk.Frame(self.right_frame, bg="white", highlightbackground="#CCCCCC", highlightthickness=1, bd=0)
        self.tree_tgb = self.create_treeview(self.tgb_container, "淘")

        # 底部配置控制栏
        bottom_frame = tk.Frame(self.root, bd=1, relief="groove")
        bottom_frame.pack(side="bottom", fill="x", pady=2, padx=4)

        # 第一行：联动选择项
        link_frame = tk.Frame(bottom_frame)
        link_frame.pack(fill="x", pady=2, padx=4)
        
        tk.Label(link_frame, text="联动选择:").pack(side="left", padx=2)
        chk_tdx = tk.Checkbutton(link_frame, text="通达信(tdx)", variable=self.link_tdx_var, command=self.save_config_settings)
        chk_tdx.pack(side="left", padx=5)
        chk_ths = tk.Checkbutton(link_frame, text="同花顺(ths)", variable=self.link_ths_var, command=self.save_config_settings)
        chk_ths.pack(side="left", padx=5)
        chk_vis = tk.Checkbutton(link_frame, text="可视化(vis)", variable=self.link_vis_var, command=self.save_config_settings)
        chk_vis.pack(side="left", padx=5)

        # 第二行：系统参数配置
        settings_frame = tk.Frame(bottom_frame)
        settings_frame.pack(fill="x", pady=2, padx=4)

        tk.Label(settings_frame, text="板块名:").pack(side="left", padx=2)
        self.entry_blk_name = ttk.Entry(settings_frame, width=12)
        self.entry_blk_name.insert(0, self.config.get("blk_name", "RQG.blk"))
        self.entry_blk_name.pack(side="left", padx=2)

        tk.Label(settings_frame, text="同步数量:").pack(side="left", padx=5)
        self.entry_limit = ttk.Entry(settings_frame, width=5)
        self.entry_limit.insert(0, str(self.config.get("limit", 50)))
        self.entry_limit.pack(side="left", padx=2)

        tk.Label(settings_frame, text="间隔(分):").pack(side="left", padx=5)
        self.entry_interval = ttk.Entry(settings_frame, width=5)
        self.entry_interval.insert(0, str(self.config.get("interval", 5)))
        self.entry_interval.pack(side="left", padx=2)

        # 绑定事件以实现自动持久化配置
        self.entry_blk_name.bind("<FocusOut>", lambda e: self.save_config_settings())
        self.entry_blk_name.bind("<Return>", lambda e: self.save_config_settings())
        self.entry_limit.bind("<FocusOut>", lambda e: self.save_config_settings())
        self.entry_limit.bind("<Return>", lambda e: self.save_config_settings())
        self.entry_interval.bind("<FocusOut>", lambda e: self.save_config_settings())
        self.entry_interval.bind("<Return>", lambda e: self.save_config_settings())

        self.btn_loop = ttk.Button(settings_frame, text="启动自动", command=self.toggle_loop)
        self.btn_loop.pack(side="left", padx=5)

        self.lbl_status = tk.Label(settings_frame, text="就绪", fg="blue", font=("Microsoft YaHei", 9, "bold"))
        self.lbl_status.pack(side="right", padx=10)

    def create_treeview(self, parent, first_col_title):
        tree = ttk.Treeview(
            parent,
            columns=("idx", "code", "name", "val"),
            show="headings",
            selectmode="browse"
        )
        tree.heading("idx", text=first_col_title)
        tree.heading("code", text="代码")
        tree.heading("name", text="名称")
        tree.heading("val", text="涨幅" if first_col_title == "花" else "涨")

        tree.column("idx", width=35, anchor="center", stretch=False)
        tree.column("code", width=65, anchor="center", stretch=False)
        tree.column("name", width=90, anchor="center", stretch=True)   # 允许随窗口拉伸
        tree.column("val", width=60, anchor="center", stretch=False)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview,
                                  style="Slim.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 颜色标签
        tree.tag_configure("up", foreground="#E02020", font=("Microsoft YaHei", 9, "bold"))
        tree.tag_configure("down", foreground="#20A020", font=("Microsoft YaHei", 9, "bold"))
        tree.tag_configure("flat", foreground="#000000", font=("Microsoft YaHei", 9))

        # 绑定点击表头排序
        for col in ("idx", "code", "name", "val"):
            tree.heading(col, command=lambda c=col, t=tree: self.sort_column(t, c, False))

        tree.sort_col = self.config.get("sort_col", None)
        tree.sort_descending = self.config.get("sort_descending", False)

        # 绑定联动事件
        tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        tree.bind("<Double-1>", self.on_tree_select)

        return tree

    def sort_column(self, tree, col, reverse, auto_restore=False):
        # 1. 提取数据项并转化为可排序的值
        l = []
        for k in tree.get_children(''):
            val = tree.set(k, col)
            l.append((val, k))
            
        def try_convert(val):
            if val is None:
                return -9999.0
            val_str = str(val).strip().replace('%', '')
            if not val_str:
                return -9999.0
            try:
                return float(val_str)
            except ValueError:
                return val_str.lower()
                
        # 2. 稳定原地排序
        l.sort(key=lambda t: try_convert(t[0]), reverse=reverse)
        
        # 3. 重新插入视图
        for index, (val, k) in enumerate(l):
            tree.move(k, '', index)
            
        # 4. 保存排序状态
        tree.sort_col = col
        tree.sort_descending = reverse
        
        if not auto_restore:
            # 手动点击时更新该列 heading，以便下次反转方向
            tree.heading(col, command=lambda: self.sort_column(tree, col, not reverse))
            
            # 同步排序到其他窗口
            all_trees = (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res)
            for other_tree in all_trees:
                if other_tree != tree:
                    self.sort_column(other_tree, col, reverse, auto_restore=True)
            
            # [OPTIMIZE] 排序时仅在内存中更新状态，不执行写盘。退出关闭时统一持久化。
            
        # 5. 更新表头的 ▲/▼ 指示器
        self.update_header_arrows(tree, col, reverse)

    def update_header_arrows(self, tree, active_col, reverse):
        # 探测当前 Tree 绑定的 first_col_title 基础名称
        first_title = "东"
        if tree == self.tree_em:
            first_title = "东"
        elif tree == self.tree_ths:
            first_title = "花"
        elif tree == self.tree_lh:
            first_title = "开"
        elif tree == self.tree_tgb:
            first_title = "淘"
        elif tree == self.tree_res:
            first_title = "合"
            
        base_headers = {
            "idx": first_title,
            "code": "代码",
            "name": "名称",
            "val": "涨幅" if first_title == "花" else "涨"
        }
        
        for col in ("idx", "code", "name", "val"):
            base_text = base_headers[col]
            if col == active_col:
                arrow = " ↓" if reverse else " ↑"
                tree.heading(col, text=f"{base_text}{arrow}")
            else:
                tree.heading(col, text=base_text)


    def on_tree_select(self, event):
        tree = event.widget
        selection = tree.selection()
        if selection:
            item = tree.item(selection[0])
            values = item.get("values")
            if values and len(values) >= 2:
                code = str(values[1]).strip().zfill(6)
                
                # 1. 联动 TDX / THS
                is_tdx = self.link_tdx_var.get()
                is_ths = self.link_ths_var.get()
                
                if is_tdx or is_ths:
                    flags = {'tdx': is_tdx, 'ths': is_ths, 'dfcf': False}
                    if get_link_manager:
                        get_link_manager().push(code, flags=flags)
                    elif self.local_sender:
                        self.local_sender.send(code)
                
                # 2. 联动可视化 (Vis / Port 26668)
                if self.link_vis_var.get():
                    threading.Thread(target=self.send_to_visualizer, args=(code,), daemon=True).start()
                    
                self.lbl_status.config(text=f"已联动: {code}", fg="darkgreen")

    def send_to_visualizer(self, code):
        IPC_HOST = '127.0.0.1'
        IPC_PORT = 26668
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((IPC_HOST, IPC_PORT))
            payload = f"CODE|{code}"
            s.send(payload.encode('utf-8'))
            s.close()
        except Exception:
            pass

    def refresh_layout(self, em_empty, ths_empty, lh_empty, res_empty, tgb_empty):
        """动态控制无数据板块的隐藏/显示"""
        # 左分栏
        self.em_container.pack_forget()
        self.left_sep.pack_forget()
        self.ths_container.pack_forget()
        
        left_visible = []
        if not em_empty:
            left_visible.append(self.em_container)
        if not ths_empty:
            left_visible.append(self.ths_container)
            
        for i, widget in enumerate(left_visible):
            widget.pack(fill="both", expand=True, pady=1)
            if i < len(left_visible) - 1:
                self.left_sep.pack(fill="x", pady=4)
            
        # 右分栏
        self.lh_container.pack_forget()
        self.right_sep1.pack_forget()
        self.res_container.pack_forget()
        self.right_sep2.pack_forget()
        self.tgb_container.pack_forget()
        
        right_visible = []
        if not lh_empty:
            right_visible.append(self.lh_container)
        if not res_empty:
            right_visible.append(self.res_container)
        if not tgb_empty:
            right_visible.append(self.tgb_container)
            
        for i, widget in enumerate(right_visible):
            widget.pack(fill="both", expand=True, pady=1)
            if i < len(right_visible) - 1:
                if i == 0:
                    self.right_sep1.pack(fill="x", pady=4)
                else:
                    self.right_sep2.pack(fill="x", pady=4)

    def clear_all_trees(self):
        for tree in (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res):
            for item in tree.get_children():
                tree.delete(item)

    def run_once_async(self):
        self.btn_refresh.config(state="disabled", text="正在查询...")
        self.lbl_status.config(text="正在获取数据...", fg="blue")
        threading.Thread(target=self._run_once_job, daemon=True).start()

    def _run_once_job(self):
        try:
            em_data = {}
            ths_data = {}
            tgb_data = {}
            lh_data = {}
            all_quotes = {}
            quotes_lock = threading.Lock()
            
            def worker_task(source_name, fetch_func, target_dict):
                try:
                    data = fetch_func()
                    if data:
                        target_dict.update(data)
                        quotes = fetch_realtime_quotes(list(data.keys()))
                        with quotes_lock:
                            all_quotes.update(quotes)
                except Exception as ex:
                    service_logger.error(f"获取 {source_name} 数据失败: {ex}")
            
            # Start the 4 threads in parallel
            t1 = threading.Thread(target=worker_task, args=("em", fetch_eastmoney, em_data), daemon=True)
            t2 = threading.Thread(target=worker_task, args=("ths", fetch_ths, ths_data), daemon=True)
            t3 = threading.Thread(target=worker_task, args=("tgb", fetch_taoguba, tgb_data), daemon=True)
            t4 = threading.Thread(target=worker_task, args=("lh", fetch_longhu, lh_data), daemon=True)
            
            t1.start()
            t2.start()
            t3.start()
            t4.start()
            
            # Wait for all of them to finish
            t1.join()
            t2.join()
            t3.join()
            t4.join()
            
            # 3. 计算人气共振得分
            resonance_results = calculate_resonance_scores(em_data, ths_data, tgb_data, lh_data)
            
            # 保存当前的共振股票代码
            limit = int(self.entry_limit.get() or "50")
            self.resonance_codes = [r['code'] for r in resonance_results[:limit]]
            
            # 4. 当更新有数据后，执行持久化缓存 (非全空)
            if em_data or ths_data or tgb_data or lh_data:
                cache_file = os.path.join(get_app_root(), "popularity_resonance_cache.json")
                try:
                    cache_data = {
                        "em_data": em_data,
                        "ths_data": ths_data,
                        "tgb_data": tgb_data,
                        "lh_data": lh_data,
                        "resonance_results": resonance_results[:limit],
                        "quotes": all_quotes,
                        "timestamp": time.time()
                    }
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, indent=4, ensure_ascii=False)
                except Exception as cache_err:
                    service_logger.error(f"写入数据缓存失败: {cache_err}")
            
            # 5. 在主线程中安全地更新所有表（包括去重过滤和整体布局）
            self.root.after(0, lambda: self.update_all_tables(em_data, ths_data, lh_data, tgb_data, resonance_results[:limit], all_quotes))
            
            # [OPTIMIZE] 后台定时抓取或查询时不执行写盘，避免频繁的磁盘IO。退出关闭时统一持久化。
            
        except Exception as e:
            self.root.after(0, lambda: self.lbl_status.config(text=f"刷新失败: {e}", fg="red"))
        finally:
            self.root.after(0, lambda: self.btn_refresh.config(state="normal", text="查询刷新"))

    def update_all_tables(self, em_data, ths_data, lh_data, tgb_data, resonance_results, quotes):
        self.clear_all_trees()

        # 1. 提取所有进入“合”表（共振表）的股票代码，用于在其他原始排行榜中做去重过滤
        resonance_set = {item["code"] for item in resonance_results}

        # 2. 定义带去重功能的单个表格填充辅助函数
        def populate(tree, data_dict):
            sorted_items = sorted(data_dict.items(), key=lambda x: x[1])
            display_rank = 1
            for _, (code, _) in enumerate(sorted_items, 1):
                # 如果该个股已被归入共振榜，则在其他表（东、花、开、淘）中过滤去重
                if code in resonance_set:
                    continue
                    
                quote = quotes.get(code, {"name": "--", "percent": 0.0})
                name = quote["name"]
                pct = quote["percent"]
                
                tag = "flat"
                if pct > 0:
                    tag = "up"
                elif pct < 0:
                    tag = "down"
                
                tree.insert("", "end", values=(display_rank, code, name, f"{pct:.2f}"), tags=(tag,))
                display_rank += 1

        # 3. 填充前4个表并过滤去重
        populate(self.tree_em, em_data)
        populate(self.tree_ths, ths_data)
        populate(self.tree_lh, lh_data)
        populate(self.tree_tgb, tgb_data)

        # 4. 填充共振“合”表
        for rank, item in enumerate(resonance_results, 1):
            code = item["code"]
            quote = quotes.get(code, {"name": "--", "percent": 0.0})
            name = quote["name"]
            pct = quote["percent"]
            
            tag = "flat"
            if pct > 0:
                tag = "up"
            elif pct < 0:
                tag = "down"
                
            self.tree_res.insert("", "end", values=(rank, code, name, f"{pct:.2f}"), tags=(tag,))

        # 5. 依据表格中实际插入的子项数量，动态隐藏/显示板块
        em_empty = len(self.tree_em.get_children()) == 0
        ths_empty = len(self.tree_ths.get_children()) == 0
        lh_empty = len(self.tree_lh.get_children()) == 0
        tgb_empty = len(self.tree_tgb.get_children()) == 0
        res_empty = len(self.tree_res.get_children()) == 0
        
        self.refresh_layout(em_empty, ths_empty, lh_empty, res_empty, tgb_empty)

        # 6. 对所有具有排序状态的表格进行排序自愈
        for tree in (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res):
            if getattr(tree, "sort_col", None) is not None:
                self.sort_column(tree, tree.sort_col, getattr(tree, "sort_descending", False), auto_restore=True)

        self.lbl_status.config(text="更新完成", fg="blue")

    def write_block_async(self):
        if not self.resonance_codes:
            messagebox.showwarning("警告", "请先执行'查询刷新'获取数据后，再写入板块！")
            return
            
        self.btn_write.config(state="disabled", text="正在写入...")
        self.lbl_status.config(text="正在写入通达信板块...", fg="blue")
        threading.Thread(target=self._write_block_job, daemon=True).start()

    def _write_block_job(self):
        try:
            blk_name = self.entry_blk_name.get().strip() or "RQG.blk"
            write_to_tdx_blocks(self.resonance_codes, blk_filename=blk_name)
            self.root.after(0, lambda: self.lbl_status.config(text=f"成功写入 {len(self.resonance_codes)} 只至 {blk_name}", fg="darkgreen"))
            # [OPTIMIZE] 写入板块时不执行写盘，退出关闭时统一持久化。
        except Exception as e:
            self.root.after(0, lambda: self.lbl_status.config(text=f"写入失败: {e}", fg="red"))
        finally:
            self.root.after(0, lambda: self.btn_write.config(state="normal", text="写入板块"))

    def toggle_loop(self):
        if not self.is_running:
            try:
                interval_min = float(self.entry_interval.get())
                if interval_min <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("错误", "刷新间隔必须是大于0的数字")
                return
                
            self.is_running = True
            self.btn_loop.config(text="停止自动")
            self.entry_interval.config(state="disabled")
            self.entry_limit.config(state="disabled")
            self.lbl_status.config(text="自动刷新已启动", fg="blue")
            
            def loop():
                while self.is_running:
                    self._run_once_job()
                    for _ in range(int(interval_min * 60)):
                        if not self.is_running:
                            break
                        time.sleep(1)
                        
            self.refresh_thread = threading.Thread(target=loop, daemon=True)
            self.refresh_thread.start()
        else:
            self.is_running = False
            self.btn_loop.config(text="启动自动")
            self.entry_interval.config(state="normal")
            self.entry_limit.config(state="normal")
            self.lbl_status.config(text="自动刷新已停止", fg="blue")

if __name__ == "__main__":
    # Windows/PyInstaller 多进程兼容性支持
    import multiprocessing
    multiprocessing.freeze_support()
    
    root = tk.Tk()
    app = PRServiceGUI(root)
    root.mainloop()
