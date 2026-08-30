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
import pandas as pd
from history_manager import QueryHistoryManager
from stock_logic_utils import test_code_against_queries
import threading
import time
import json
import socket
from datetime import datetime, timedelta
from ipc_sync_manager import IPCSyncManager
from sys_utils import get_app_root
from JohnsonUtil import commonTips as cct
# 导入 tkcalendar 库支持，高保真还原日历选择器
try:
    import JohnsonUtil.tkcalendar_patch
    from tkcalendar import DateEntry
    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False

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


class _DynamicIPCSyncProxy:
    """动态端口 IPC 行情代理类：无需长期占用固定端口，按需或自动刷新时开启动态端口拉取数据"""
    def __init__(self, owner):
        self.owner = owner

    def get_current_df(self):
        return self.owner.get_current_df()

    def request_full_sync(self):
        return self.owner.request_dynamic_ipc_sync()

    def stop(self):
        pass


class PRServiceGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("人气综合排行榜2.22")
        
        # 加载配置（必须在设置 geometry 前加载）
        self.config = self.load_config_settings()
        
        # 恢复窗口位置与大小，默认 780x760
        saved_geo = self.config.get("geometry", "780x760")
        try:
            self.root.geometry(saved_geo)
        except Exception:
            self.root.geometry("780x760")
        
        self.is_running = False
        self.refresh_thread = None
        self.resonance_codes = []  # 缓存当前的共振股票代码
        self.selected_concept = None  # 用于保存当前选中的概念过滤条件
        self._block_cache = {}        # 行业板块特征缓存
        self._last_test_df_hits = None  # 缓存的用于 Hit 测试的 DataFrame
        self.current_date = time.strftime("%Y-%m-%d")
        self._last_realtime_today = self.current_date
        
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
        # 初始化过滤公式表达式
        self.query_expr = ""
            
        self.create_widgets()

        # 实例化 QueryHistoryManager 和独立 Toplevel 窗口 (只读模式)
        self.history_win = tk.Toplevel(self.root)
        self.history_win.title("人气过滤公式历史管理器 (只读模式)")
        self.history_win.geometry("800x480")
        self.history_win.withdraw()  # 默认隐藏
        
        def on_history_win_close():
            self.history_win.withdraw()
            # [只读模式] 仅隐藏窗口，不进行任何历史写盘保存
                
        self.history_win.protocol("WM_DELETE_WINDOW", on_history_win_close)

        # 兼容打包环境，统一使用与主程序完全一致的 search_history.json 路径
        try:
            from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
        except ImportError:
            SEARCH_HISTORY_FILE = os.path.join(get_app_root(), "datacsv", "search_history.json")
        self.query_manager = QueryHistoryManager(
            root=self.history_win,
            search_var5=self.query_var,
            search_combo5=self.query_combo,
            auto_run=False,
            history_file=SEARCH_HISTORY_FILE,
            sync_history_callback=self.sync_history_from_QM,
            test_callback=self.on_test_code
        )
        
        # [只读模式强约束] 人气综合模块仅读取 search_history.json 作为过滤公式，绝不覆写修改
        def _read_only_save(*args, **kwargs):
            service_logger.debug("[QueryHistoryManager] 人气综合处于只读模式，忽略写盘操作")
            return
        self.query_manager.save_search_history = _read_only_save
        
        # 刚初始化完，将编辑器内置 Frame 放置到 Toplevel 容器中
        if hasattr(self.query_manager, 'editor_frame'):
            self.query_manager.editor_frame.pack(fill="both", expand=True)
            
        # 默认选中并加载 history5 分组
        self.history_selector.set("history5")
        self._on_history_group_changed()

        # 初始化动态 IPC 行情同步管理器与内存行情快照 (不用长期占用固定端口)
        self.current_df = None
        self.df_lock = threading.Lock()
        self._ipc_sync_in_progress = False
        self.sync_manager = _DynamicIPCSyncProxy(self)
        
        # 启动后后台发起带退避重试的动态端口 IPC 数据同步 (提升启动成功率)
        def _start_initial_ipc_sync():
            for attempt in range(3):
                df = self.request_dynamic_ipc_sync(timeout=8.0)
                if df is not None and not df.empty:
                    service_logger.info(f"[IPC 启动同步] 第 {attempt + 1} 次尝试成功获取 IPC 行情数据 ({len(df)} 行)")
                    break
                time.sleep(2.0 * (attempt + 1))

        threading.Thread(target=_start_initial_ipc_sync, daemon=True).start()
        
        # 启动交易时间内后台轻量级 IPC 动态行情定时轮询更新器
        self._start_ipc_polling_loop()
        
        # 初始化布局 (全部为空，所以先隐藏)
        self.refresh_layout(em_empty=True, ths_empty=True, lh_empty=True, res_empty=True, tgb_empty=True)

        # 尝试加载缓存数据并恢复表格
        self.load_cached_data()

        # 监听窗口关闭事件，确保最终配置得到持久化保存
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 初始化自选股版本并启动心跳轮询
        try:
            from global_favorites import GlobalFavoriteManager
            self._last_favorites_version = GlobalFavoriteManager().version
        except Exception as e:
            service_logger.debug(f"初始化自选股轮询失败: {e}")
        
        if hasattr(self, 'root'):
            self.root.after(500, self._poll_favorites_loop)

        # 自动同步收盘数据状态初始化与定时器注册
        self._auto_save_fail_count = 0
        self._last_auto_save_attempt_time = 0.0
        self._final_post_market_saved_date = None
        # 绑定 Alt-c / Alt-C 全局一键挂单快捷键 (已取消空格触发)
        if hasattr(self, 'root'):
            self.root.bind("<Alt-c>", self.on_quick_order)
            self.root.bind("<Alt-C>", self.on_quick_order)

        # 启动初始化自动加载：若配置中上一次处于“启动自动”状态，自动恢复唤起自动刷新
        if self.config.get("auto_refresh", False):
            if hasattr(self, 'root'):
                self.root.after(1000, lambda: self.toggle_loop() if not getattr(self, "is_running", False) else None)

    def _format_history_item_local(self, item):
        """人气共振专用格式化：备注 | [Hit: N] | 逻辑"""
        if not isinstance(item, dict): 
            return str(item)
        q = item.get("query", "").strip()
        q = " ".join(q.split())  # 压缩空白
        note = item.get("note", "").strip()
        hit = item.get("hit", "")
        parts = []
        if note: 
            parts.append(note)
        if hit != "" and hit is not None: 
            parts.append(f"[Hit: {hit}]")
        parts.append(q)
        return "  |  ".join(parts)

    def get_test_df_for_hits(self):
        # 优先复用刚刚在 update_all_tables 里或者其它地方已经构建好的 test_df 缓存
        if hasattr(self, '_last_test_df_hits') and self._last_test_df_hits is not None and not self._last_test_df_hits.empty:
            return self._last_test_df_hits
            
        import pandas as pd
        # 1. 收集当前五个 Treeview 表格中所有的人气榜股票代码
        all_codes = set()
        for tree in (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res):
            for iid in tree.get_children():
                vals = tree.item(iid, "values")
                if vals and len(vals) > 1:
                    all_codes.add(str(vals[1]).strip().zfill(6))
                     
        # 2. 从全量行情中筛选出属于当前人气榜个股的切片
        test_df = pd.DataFrame()
        if hasattr(self, "sync_manager") and all_codes:
            full_df = self.sync_manager.get_current_df()
            if full_df is not None and not full_df.empty:
                valid_codes = [c for c in all_codes if c in full_df.index]
                if valid_codes:
                    test_df = full_df.loc[valid_codes].copy()
                     
        # 3. Fallback 退避机制
        if test_df.empty and all_codes:
            test_df = pd.DataFrame(index=list(all_codes))
            test_df['name'] = ""
            test_df['percent'] = 0.0
            test_df['trade'] = 0.0
            test_df['dff2'] = 0.0
            test_df['dff3'] = 0.0
            test_df['Rank'] = 0
            test_df['category'] = ""
            for code_str in test_df.index:
                block_str = self._block_cache.get(code_str, '--')
                test_df.at[code_str, 'category'] = block_str
                
        # 4. 兼容异动字段别名
        if not test_df.empty:
            mapping = {
                '价格': 'close', '最新价': 'close', '现价': 'close', 
                '涨幅': 'pct', 
                '量': 'volume', '成交量': 'volume',
                '成交额': 'turnover',
                '最高': 'high', '最低': 'low', '开盘': 'open',
                '板块': 'category', '异动类型': 'category', 'hy': 'category'
            }
            for cn, en in mapping.items():
                if cn in test_df.columns and en not in test_df.columns:
                    test_df[en] = test_df[cn]
            # OHLC 字段兜底
            if 'close' in test_df.columns:
                for col in ['open', 'high', 'low']:
                    if col not in test_df.columns:
                        test_df[col] = test_df['close']
                        
        self._last_test_df_hits = test_df
        return test_df

    def calculate_history_hits_ui(self):
        """计算当前历史记录的命中数并更新下拉列表"""
        if not hasattr(self, 'query_manager'):
            from stock_logic_utils import toast_message
            toast_message(self.root, "⚠️ 历史管理器未初始化")
            return
            
        test_df = self.get_test_df_for_hits()
        if test_df.empty:
            from stock_logic_utils import toast_message
            toast_message(self.root, "⚠️ 数据未就绪或未加载人气榜")
            return

        group = self.history_selector.get()
        target = getattr(self.query_manager, group, [])
        if not target: 
            return

        from stock_logic_utils import test_code_against_queries, toast_message
        
        # 调用具备缺失列自愈与防爆设计的 test_code_against_queries 进行批量测评
        enriched_results = test_code_against_queries(test_df, target)
        
        new_values = []
        for i, item in enumerate(target):
            hit_count = 0
            if i < len(enriched_results):
                hit_count = enriched_results[i].get("hit", 0)
            # 保存命中数到内存
            item["hit"] = hit_count
            
            # 采用统一的显示格式化逻辑
            display = self._format_history_item_local(item)
            new_values.append(display)
            
        self.query_combo['values'] = new_values
        
        # 自动刷新当前选中的显示（以反映最新的命中数）
        current_val = self.query_var.get()
        if current_val:
            # 提取当前纯 query
            raw_q = self._get_real_query()
            # 在新列表中寻找对应的记录
            for idx, item in enumerate(target):
                if item.get("query") == raw_q:
                    new_display = self._format_history_item_local(item)
                    self.query_var.set(new_display)
                    break

        toast_message(self.root, f"✅ 策略命中统计完成 (n={len(target)})")
        
        # 同步更新编辑器里的 Treeview（如果打开了）
        if self.query_manager:
            self.query_manager.refresh_tree()

    def _on_history_group_changed(self, event=None):
        group = self.history_selector.get()
        if hasattr(self, 'query_manager'):
            self.query_manager.current_key = group
            self.query_manager.current_history = getattr(self.query_manager, group)
            if hasattr(self.query_manager, 'combo_group') and self.query_manager.combo_group.winfo_exists():
                self.query_manager.combo_group.set(group)
                self.query_manager.refresh_tree()
                
        h_list = []
        if hasattr(self, 'query_manager'):
            h_list = getattr(self.query_manager, group, [])
            
        formatted_list = []
        for item in h_list:
            display_text = self._format_history_item_local(item)
            if display_text:
                formatted_list.append(display_text)
        self.query_combo['values'] = formatted_list
        if formatted_list:
            self.query_combo.set(formatted_list[0])
        else:
            self.query_combo.set("")

    def _get_real_query(self):
        text = self.query_var.get().strip()
        if "  |  " in text:
            return text.split("  |  ")[-1].strip()
        return text

    def on_toolbar_dna_click(self):
        """点击工具栏 🧬 DNA 审计 按钮：优先获取最新处于活动/点击焦点的 Treeview 实例及其后的 20 只个股"""
        # 1. 优先获取最近处于活动/点击焦点的 Treeview 实例
        target_tree = getattr(self, '_last_active_tree', None)
        selected_item = None
        
        # 2. 如果 target_tree 有选中项，我们优先使用它
        if target_tree and target_tree.winfo_exists():
            sel = target_tree.selection()
            if sel:
                selected_item = sel[0]
                
        # 3. 如果没找到选中项或 target_tree 不存在，我们重新在所有 treeview 中寻找当前有选中项的表格
        if not target_tree or not selected_item:
            all_trees = []
            # 如果主界面有 concept_tree (板块个股弹窗) 且处于打开/可见状态，优先检查它
            concept_tree = getattr(self, 'concept_tree', None)
            if concept_tree and concept_tree.winfo_exists() and concept_tree.winfo_viewable():
                all_trees.append(concept_tree)
            all_trees.extend([self.tree_res, self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb])
            
            for tree in all_trees:
                if tree and tree.winfo_exists():
                    sel = tree.selection()
                    if sel:
                        target_tree = tree
                        selected_item = sel[0]
                        # 更新为最近活动
                        self._last_active_tree = tree
                        break
                        
        # 4. 如果依然没有任何 Treeview 选中，我们默认取可见的、且有数据的第一个 Treeview 的首只股票
        if not target_tree or not selected_item:
            all_trees = []
            concept_tree = getattr(self, 'concept_tree', None)
            if concept_tree and concept_tree.winfo_exists() and concept_tree.winfo_viewable():
                all_trees.append(concept_tree)
            all_trees.extend([self.tree_res, self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb])
            
            for tree in all_trees:
                if tree and tree.winfo_exists() and tree.winfo_viewable() and tree.get_children():
                    target_tree = tree
                    selected_item = tree.get_children()[0]
                    self._last_active_tree = tree
                    break
                    
        # 5. 如果实在没有任何数据，直接提示并退出
        if not target_tree or not selected_item:
            from tkinter import messagebox
            messagebox.showinfo("信息", "当前无可用的人气个股进行 DNA 审计", parent=self.root)
            return
            
        # 6. 获取所选个股及其后面的最多 20 个个股（共计最多 21 个个股）
        children = target_tree.get_children()
        try:
            curr_idx = children.index(selected_item)
            target_items = children[curr_idx:curr_idx + 21]
        except ValueError:
            target_items = [selected_item]
            
        cols = list(target_tree["columns"])
        code_idx = cols.index("code") if "code" in cols else 1
        name_idx = cols.index("name") if "name" in cols else 2
        
        code_to_name = {}
        for t_item in target_items:
            t_values = target_tree.item(t_item, "values")
            if t_values and len(t_values) > max(code_idx, name_idx):
                t_code = str(t_values[code_idx]).strip().zfill(6)
                t_name = str(t_values[name_idx]).strip()
                if t_name.startswith("★ "):
                    t_name = t_name[len("★ "):]
                code_to_name[t_code] = t_name
                
        if code_to_name:
            self._run_dna_audit_batch(code_to_name, resample='d')

    def apply_filter(self, event=None):
        query = self._get_real_query()
        self.query_expr = query
        
        # [只读模式] 仅作为即时过滤条件应用，不修改/追加历史记录，不触发写盘
                    
        if hasattr(self, '_last_data_cache') and self._last_data_cache:
            c = self._last_data_cache
            self.update_all_tables(
                c["em_data"],
                c["ths_data"],
                c["lh_data"],
                c["tgb_data"],
                c["resonance_results"],
                c["quotes"]
            )
        else:
            self.run_once_async()

    def clear_filter(self):
        self.query_var.set("")
        self.query_expr = ""
        if hasattr(self, '_last_data_cache') and self._last_data_cache:
            c = self._last_data_cache
            self.update_all_tables(
                c["em_data"],
                c["ths_data"],
                c["lh_data"],
                c["tgb_data"],
                c["resonance_results"],
                c["quotes"]
            )
        else:
            self.run_once_async()

    def manage_history(self):
        if hasattr(self, 'history_win'):
            self.history_win.deiconify()
            self.history_win.lift()
            self.history_win.focus_force()
            if hasattr(self, 'query_manager'):
                self.query_manager.refresh_tree()

    def sync_history_from_QM(self, **kwargs):
        self._on_history_group_changed()
        source = kwargs.get("source", "")
        selected_query = kwargs.get("selected_query")
        if source == "use" and selected_query:
            found = False
            for val in self.query_combo['values']:
                if val == selected_query or val.endswith(f"|  {selected_query}"):
                    self.query_combo.set(val)
                    found = True
                    break
            if not found:
                self.query_combo.set(selected_query)
            self.apply_filter()

    def on_test_code(self, query=None, onclick=False):
        df_cache = self.get_test_df_for_hits()
        if df_cache.empty:
            return []
        
        # 将过滤后的人气榜个股专属数据集同步给 query_manager，供其内部使用
        if hasattr(self, 'query_manager'):
            self.query_manager.df_all = df_cache

        if onclick:
            # 临时解绑 test_callback 避免无限递归，然后调用默认测试逻辑
            if hasattr(self, 'query_manager'):
                old_cb = self.query_manager.test_callback
                self.query_manager.test_callback = None
                try:
                    self.query_manager.on_test_code(onclick=True)
                    self.calculate_history_hits_ui()
                finally:
                    self.query_manager.test_callback = old_cb
            return []

        from stock_logic_utils import test_code_against_queries
        return test_code_against_queries(df_cache, [{"query": query}])


    def on_close(self):
        try:
            self.sync_manager.stop()
        except Exception:
            pass
        self.save_config_settings()
        
        # [只读模式] 关闭时无需保存 search_history
        if hasattr(self, 'history_win') and self.history_win.winfo_exists():
            try:
                self.history_win.destroy()
            except Exception:
                pass

        # 在退出时同步保存一次最新的 block_cache
        cache_file = os.path.join(get_app_root(), "popularity_resonance_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                cache["block_cache"] = getattr(self, "_block_cache", {})
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
        self.root.destroy()

    def _start_ipc_polling_loop(self):
        """交易时间内后台轻量级 IPC 动态行情定时轮询更新器"""
        def polling_worker():
            while getattr(self, "root", None):
                try:
                    time.sleep(30)  # 每 30 秒后台静默轮询一次
                    from JohnsonUtil import commonTips as cct
                    if cct.get_work_time():
                        # 若当前未在手动/自动主抓取中，拉取最新 IPC 行情切片
                        if not getattr(self, '_ipc_sync_in_progress', False):
                            refresh_thread = getattr(self, 'refresh_thread', None)
                            if not (refresh_thread and refresh_thread.is_alive()):
                                service_logger.debug("[IPC 定时轮询] 交易时间内自动轮询拉取最新 IPC 行情数据...")
                                self.request_dynamic_ipc_sync(timeout=6.0)
                except Exception as e:
                    service_logger.debug(f"[IPC 定时轮询] 异常: {e}")

        threading.Thread(target=polling_worker, daemon=True).start()

    def _poll_favorites_loop(self):
        if not hasattr(self, 'root') or not self.root:
            return
        try:
            from global_favorites import GlobalFavoriteManager
            current_version = GlobalFavoriteManager().version
            if current_version != getattr(self, '_last_favorites_version', 0):
                self._last_favorites_version = current_version
                self._refresh_ui_favorites()
        except Exception as e:
            service_logger.debug(f"Error in poll_favorites_loop: {e}")
        finally:
            try:
                self.root.after(500, self._poll_favorites_loop)
            except Exception:
                pass

    def _refresh_ui_favorites(self):
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            return
            
        all_trees = (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res)
        for tree in all_trees:
            for iid in tree.get_children():
                vals = tree.item(iid, "values")
                if not vals or len(vals) < 3:
                    continue
                code = str(vals[1]).strip().zfill(6)
                name = str(vals[2]).strip()
                
                is_fav = code in fav_stocks
                clean_name = name
                if name.startswith("★ "):
                    clean_name = name[len("★ "):]
                
                new_name = f"★ {clean_name}" if is_fav else clean_name
                
                curr_tags = list(tree.item(iid, "tags") or [])
                has_fav_tag = "favorite" in curr_tags
                
                need_update = (name != new_name) or (is_fav != has_fav_tag)
                if need_update:
                    new_vals = list(vals)
                    new_vals[2] = new_name
                    tree.item(iid, values=tuple(new_vals))
                    
                    if is_fav and "favorite" not in curr_tags:
                        curr_tags.append("favorite")
                    elif not is_fav and "favorite" in curr_tags:
                        curr_tags.remove("favorite")
                    tree.item(iid, tags=tuple(curr_tags))

    DEFAULT_COLUMN_WIDTHS = {
        "idx": 32,
        "code": 58,
        "name": 72,
        "val": 52,
        "price": 56,
        "ladder": 95,
        "bid_p": 78,
        "pioneer": 82,
        "decision": 96,
        "dff2": 46,
        "dff3": 46,
        "rank": 42,
        "dff": 48,
        "slope": 48,
        "win": 40,
        "red": 40,
        "ch_bc": 44,
        "MainL": 50,
        "ch_bc2": 44,
        "MainU": 50
    }

    # 最小安全列宽（防止文字被严重压缩变形截断）
    MIN_COLUMN_WIDTHS = {
        "idx": 26,
        "code": 50,
        "name": 62,
        "val": 44,
        "price": 48,
        "ladder": 75,
        "bid_p": 65,
        "pioneer": 68,
        "decision": 75,
        "dff2": 38,
        "dff3": 38,
        "rank": 35,
        "dff": 40,
        "slope": 40,
        "win": 35,
        "red": 35,
        "ch_bc": 38,
        "MainL": 42,
        "ch_bc2": 38,
        "MainU": 42
    }

    def _adjust_tree_column_widths(self, tree):
        """保持 Treeview 自身 stretch 自然渲染，不执行递归强制改写"""
        pass

    def _on_tree_column_drag_release(self, event, tree):
        """用户拖动表头分隔线调整列宽后，精准单列同步并持久化"""
        try:
            # 延时 40ms 等 Tkinter 原生完成列宽几何变化
            if hasattr(self, 'root') and self.root:
                self.root.after(40, lambda: self._sync_column_widths_from_tree(tree))
        except Exception:
            pass

    def _sync_column_widths_from_tree(self, source_tree):
        """仅同步真正被用户手动拖动改变宽度的列，防止全局覆盖污染"""
        try:
            if not source_tree or not source_tree.winfo_exists():
                return
            saved_widths = self.config.setdefault("column_widths", {})
            all_trees = [t for t in (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res) if t and t.winfo_exists()]
            changed = False
            for col in source_tree.cget("columns"):
                try:
                    cur_w = int(source_tree.column(col, "width"))
                    old_w = saved_widths.get(col, self.DEFAULT_COLUMN_WIDTHS.get(col, 48))
                    min_safe_w = self.MIN_COLUMN_WIDTHS.get(col, 35)
                    # 只有当宽度发生实质变化且大于最小安全宽度时才更新
                    if cur_w >= min_safe_w and abs(cur_w - old_w) >= 3:
                        saved_widths[col] = cur_w
                        changed = True
                        for other_tree in all_trees:
                            if other_tree != source_tree:
                                try:
                                    other_tree.column(col, width=cur_w)
                                except Exception:
                                    pass
                        if hasattr(self, 'concept_tree') and self.concept_tree and self.concept_tree.winfo_exists():
                            try:
                                self.concept_tree.column(col, width=cur_w)
                            except Exception:
                                pass
                except Exception:
                    pass
            if changed:
                self.save_config_settings()
                service_logger.debug(f"[列宽同步] 已精准同步并持久化列宽配置: {saved_widths}")
        except Exception as e:
            service_logger.debug(f"Sync column widths failed: {e}")

    def _normalize_concept_name(self, name):
        if not name:
            return ""
        import re
        # 将中文括号标准化为英文括号并移除两侧空白
        n = str(name).replace('（', '(').replace('）', ')').strip()
        # 去除诸如 " (15只)" 或 " (15)" 的数量后缀
        n = re.sub(r'\s*\(\d+只?\)\s*$', '', n)
        return n

    def _is_noise_concept(self, name_str):
        NOISE_CONCEPTS = {
            "深股通", "港股通", "沪股通", "国企改革", "央企国企改革", "融资融券", "标普道琼斯A股", 
            "富时罗素概念股", "MSCI概念", "转融券标的", "机构重仓", "证金持股", "汇金持股", 
            "预盈预增", "破净股", "ST板块", "参股新三板", "创业板设", "科创板", "地方国企改革", 
            "央企改革", "壳资源", "新股与次新股", "昨日涨停", "昨日连板", "百元股", "中字头",
            "低价股", "破发股", "外资背景", "QFII重仓", "社保重仓", "核心资产", "新三板",
            "深成指股", "沪深300股", "上证180股", "上证50股", "创业300股", "中证500", "成分股",
            "高送转", "含可转债", "国家队持股", "地方政府平台", "央企控股", "军工改革",
            "中报", "中报送转", "季报", "年报", "一季报", "三季报", "业绩预增", "预增", "预亏",
            "预降预亏", "送转股份", "业绩补偿"
        }
        if name_str in NOISE_CONCEPTS:
            return True
        for keyword in ("改革", "股通", "成指", "重仓", "持股", "融资", "昨日", "送转", "转债", "指数", "成分", "中报", "预增", "业绩", "季报", "年报", "预盈", "预亏"):
            if keyword in name_str:
                return True
        return False

    def show_context_menu(self, event):
        tree = event.widget
        # 选中鼠标右键点击的项
        item_id = tree.identify_row(event.y)
        if not item_id:
            return
        tree.selection_set(item_id)
        tree.focus(item_id)
        
        values = tree.item(item_id, "values")
        if not values or len(values) < 2:
            return
            
        cols = list(tree["columns"])
        code_idx = cols.index("code") if "code" in cols else 1
        name_idx = cols.index("name") if "name" in cols else 2

        if len(values) <= max(code_idx, name_idx):
            return

        code = str(values[code_idx]).strip().zfill(6)
        name = str(values[name_idx]).strip()
        if name.startswith("★ "):
            name = name[len("★ "):]
            
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            is_fav = code in fav_mgr.get_favorite_stocks()
        except Exception:
            is_fav = False
            fav_mgr = None
            
        menu = tk.Menu(self.root, tearoff=0)

        # ⚡ 闪电买入直连
        menu.add_command(
            label=f"⚡ 闪电买入 ({code} {name}) [Alt+C]",
            command=self.on_quick_order
        )
        menu.add_separator()

        # 📋 复制股票代码
        menu.add_command(
            label=f"📋 复制代码 ({code})",
            command=lambda: self.copy_code_to_clipboard(code)
        )
        menu.add_separator()

        # [NEW] 查找此个股所属的最强板块（股票只数最多）并支持右键一键打开
        block_str = getattr(self, '_block_cache', {}).get(code, "")
        if block_str and block_str not in ("--", "nan", "None"):
            import re
            cats = [c.strip() for c in re.split(r'[;；,，/|]', block_str) if c.strip()]
            if cats:
                # 仅保留前 5 个最核心的主流概念（黄金概念）进行筛选与排序
                main_cats = cats[:5]
                scores_dict = getattr(self, "_all_concept_scores", {})
                
                def get_cat_strength(cat_name):
                    norm_cat = self._normalize_concept_name(cat_name)
                    max_c = 0
                    for k, count in scores_dict.items():
                        if self._normalize_concept_name(k) == norm_cat:
                            max_c = max(max_c, count)
                    return max_c
                
                # 双重优先级排序：非低优先级(0)排前面，低优先级(1)排后面；在此基础上按强度（只数）降序排列
                main_cats.sort(key=lambda c: (1 if self._is_noise_concept(c) else 0, -get_cat_strength(c)))
                
                # 获取前 3 个最强的实际意义板块并动态展示
                top3_cats = main_cats[:3]
                for strongest_cat in top3_cats:
                    strength_num = get_cat_strength(strongest_cat)
                    menu.add_command(
                        label=f"📂 查看最强板块个股 ({strongest_cat}:{strength_num}只)", 
                        command=lambda name=strongest_cat: self.show_concept_top10_window(name)
                    )
                menu.add_separator()

        # ====================
        # [🚀 NEW] DNA 专项审计 (默认选中 code 的前 20)
        # ====================
        children = tree.get_children()
        try:
            curr_idx = children.index(item_id)
            target_items = children[curr_idx:curr_idx + 21]
        except ValueError:
            target_items = [item_id]
            
        code_to_name = {}
        for t_item in target_items:
            t_values = tree.item(t_item, "values")
            if t_values and len(t_values) > max(code_idx, name_idx):
                t_code = str(t_values[code_idx]).strip().zfill(6)
                t_name = str(t_values[name_idx]).strip()
                if t_name.startswith("★ "):
                    t_name = t_name[len("★ "):]
                code_to_name[t_code] = t_name

        if code_to_name:
            menu.add_command(
                label=f"🧬 DNA 专项审计 ({len(code_to_name)}只, 默认: D)",
                command=lambda: self._run_dna_audit_batch(code_to_name, resample='d')
            )
            menu.add_separator()

        if not is_fav:
            menu.add_command(label=f"★ 添加重点关注 ({name})", command=lambda: self.add_to_favorites(code))
        else:
            menu.add_command(label=f"☆ 取消重点关注 ({name})", command=lambda: self.remove_from_favorites(code))
            
        menu.add_separator()
        menu.add_command(label="⚖️ 垂直分隔栏居中 (50%)", command=self.reset_sash_center)

        menu.post(event.x_root, event.y_root)

    def copy_code_to_clipboard(self, code):
        """复制股票代码到剪贴板并更新状态栏提示"""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(code)
            self.root.update()
            if hasattr(self, 'lbl_status'):
                self.lbl_status.config(text=f"已复制代码: {code}", fg="darkgreen")
        except Exception as e:
            service_logger.error(f"复制代码到剪贴板失败: {e}")

    def on_copy_shortcut(self, event):
        """表格 Ctrl+C 快捷键响应"""
        try:
            tree = event.widget
            sel = tree.selection()
            if sel:
                vals = tree.item(sel[0], "values")
                cols = list(tree["columns"])
                code_idx = cols.index("code") if "code" in cols else 1
                if vals and len(vals) > code_idx:
                    code = str(vals[code_idx]).strip().zfill(6)
                    self.copy_code_to_clipboard(code)
        except Exception as e:
            service_logger.error(f"快捷键复制代码失败: {e}")

    def add_to_favorites(self, code):
        try:
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().add_favorite_stock(code)
            self.lbl_status.config(text=f"已添加重点关注: {code}", fg="darkgreen")
        except Exception as e:
            messagebox.showerror("错误", f"添加重点关注失败: {e}")

    def remove_from_favorites(self, code):
        try:
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().remove_favorite_stock(code)
            self.lbl_status.config(text=f"已取消重点关注: {code}", fg="blue")
        except Exception as e:
            messagebox.showerror("错误", f"取消重点关注失败: {e}")

    def get_current_df(self):
        """线程安全获取内存中最新已拉取的行情 DataFrame"""
        with self.df_lock:
            if self.current_df is not None and not self.current_df.empty:
                return self.current_df.copy()
        return None

    def _find_available_port(self, candidate_ports=None):
        import socket
        if candidate_ports is None:
            candidate_ports = [26685, 26686, 26687, 26688, 26689, 26690, 26691, 26692, 26693, 26694, 26695]
        for p in candidate_ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                s.bind(('127.0.0.1', p))
                s.close()
                return p
            except Exception:
                continue
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('127.0.0.1', 0))
            assigned_port = s.getsockname()[1]
            s.close()
            return assigned_port
        except Exception:
            return 26685

    def request_dynamic_ipc_sync(self, timeout=8.0):
        """自动刷新或更新数据时，开启动态端口向主程序拉取全量行情数据包，接收解包完后即刻物理关闭释放端口"""
        if getattr(self, '_ipc_sync_in_progress', False):
            return self.get_current_df()
        self._ipc_sync_in_progress = True

        dyn_port = self._find_available_port()
        service_logger.info(f"[IPC 动态端口] 自动开启临时动态端口 Port={dyn_port} 获取行情数据...")

        received_container = []
        def _dynamic_cb(df):
            if df is not None and not df.empty:
                received_container.append(df)
                with self.df_lock:
                    self.current_df = df
                try:
                    self.on_realtime_data_updated(df)
                except Exception as e:
                    service_logger.debug(f"实时数据更新回调异常: {e}")

        temp_mgr = IPCSyncManager(port=dyn_port, data_callback=_dynamic_cb, logger=service_logger)
        try:
            temp_mgr.start()
            if getattr(temp_mgr, '_bind_event', None):
                temp_mgr._bind_event.wait(timeout=0.5)

            # 通过命名管道向 TK 发送包含动态端口的 REQ_FULL_SYNC 指令 (强行发包，避免被防刷冷却逻辑误拦截)
            temp_mgr.request_full_sync(force=True)

            start_t = time.time()
            while time.time() - start_t < timeout:
                if received_container or temp_mgr.get_current_df() is not None:
                    df_got = temp_mgr.get_current_df()
                    if df_got is not None and not df_got.empty:
                        with self.df_lock:
                            self.current_df = df_got
                        service_logger.info(f"[IPC 动态端口] 成功通过 Port={dyn_port} 接收 {len(df_got)} 行最新数据 (耗时 {time.time()-start_t:.2f}s)，即刻释放端口")
                        break
                time.sleep(0.1)
        except Exception as e:
            service_logger.error(f"动态端口获取 IPC 数据异常: {e}")
        finally:
            # 用完立即停止物理 Socket 监听并关闭释放端口！
            temp_mgr.stop()
            self._ipc_sync_in_progress = False

        return self.get_current_df()

    def on_realtime_data_updated(self, df):
        """当主程序通过 Socket 推送最新的 DataFrame 时的回调"""
        self.root.after(0, lambda: self.refresh_realtime_fields(df))

    def refresh_realtime_fields(self, df=None):
        today = time.strftime("%Y-%m-%d")
        current_view_date = self.current_date
        
        # 💥 [NEW] 24/7 运行支持：如果系统日期已跨天（即今天不同于上一次 the 系统日期），且前态仍处于上一个同步日，自动切换界面日期至今日，防止拦截更新
        if current_view_date != today:
            last_realtime_today = getattr(self, "_last_realtime_today", None)
            if last_realtime_today and last_realtime_today != today:
                if current_view_date == last_realtime_today:
                    service_logger.info(f"检测到系统跨天(由 {last_realtime_today} 跨至 {today})，自动同步界面日期为今日，避免实时行情被拦截。")
                    self.current_date = today
                    self._last_realtime_today = today
                    def _update_ui_date():
                        if hasattr(self, 'date_entry'):
                            try:
                                dt_today = datetime.strptime(today, "%Y-%m-%d")
                                self.date_entry.set_date(dt_today)
                            except Exception:
                                pass
                        elif hasattr(self, 'date_var'):
                            self.date_var.set(today)
                    self.root.after(0, _update_ui_date)
                    current_view_date = today

        # 核心防御：若当前查看的并非今天的数据（处于历史复盘状态），直接拦截并忽略实时行情的渲染和板块统计更新，防止历史数据被覆盖
        if current_view_date != today:
            return

        # 成功更新今日实时行情，同步更新 last_realtime_today
        self._last_realtime_today = today

        if df is None:
            df = self.sync_manager.get_current_df()
        if df is None or df.empty:
            return

        _, _, _extra_cols = self._get_all_cols()
        # 实时推送时重新将列配置为实时的自定义列
        for t, title in ((self.tree_em, "东"), (self.tree_ths, "花"), (self.tree_lh, "龙"), (self.tree_tgb, "淘"), (self.tree_res, "合")):
            self._reconfigure_tree_columns(t, title, _extra_cols)

        BASE_UPDATE_COUNT = 12  # idx/code/name/val/price/ladder/bid_p/pioneer/decision/dff2/dff3/rank

        # 创建用于统计的字典
        all_stocks_for_stats = {}

        all_trees = (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res)
        for tree in all_trees:
            for iid in tree.get_children():
                old_vals = tree.item(iid, "values")
                if not old_vals or len(old_vals) < 2:
                    continue
                code = old_vals[1]
                code_str = str(code).strip().zfill(6)
                
                # 获取旧涨幅和价格，防止 df 中没有该股票时显示为空
                pct = 0.0
                try:
                    pct = float(str(old_vals[3]).replace('%', ''))
                except Exception:
                    pass
                price_str = str(old_vals[4])
                row = None
                
                if code_str in df.index:
                    try:
                        row = df.loc[code_str]
                        import pandas as pd
                        if isinstance(row, pd.DataFrame):
                            row = row.iloc[0]

                        pct = float(row.get('percent', row.get('ratio', pct)))
                        price = float(row.get('trade', row.get('close', row.get('price', 0.0))))
                        price_str = f"{price:.2f}"
                        dff2 = float(row.get('dff2', row.get('DFF2', 0.0)))
                        dff3 = float(row.get('dff3', row.get('DFF3', 0.0)))
                        rank = int(row.get('Rank', row.get('rank', 0)))
                        block = str(row.get('category', row.get('blockname', row.get('hy', '--'))))
                        if block == 'nan' or block == 'None':
                            block = '--'

                        # 更新 _block_cache（不写进 Treeview）
                        if block and block != '--':
                            if not hasattr(self, '_block_cache'):
                                self._block_cache = {}
                            self._block_cache[code_str] = block

                        new_vals = list(old_vals)
                        while len(new_vals) < BASE_UPDATE_COUNT:
                            new_vals.append("")

                        # 计算/继承 4 大决策列
                        ladder_role = str(new_vals[5]) if len(new_vals) > 5 and new_vals[5] not in ("", "--") else (
                            "🔥 强势首板" if pct >= 9.8 else ("🚀 冲锋冲板" if pct >= 5.0 else "⏱️ 潜伏震荡")
                        )
                        bid_p_str = str(new_vals[6]) if len(new_vals) > 6 and new_vals[6] not in ("", "--") else "买压 80%"
                        pioneer_str = str(new_vals[7]) if len(new_vals) > 7 and new_vals[7] not in ("", "--") else (
                            "💎 逆势破局" if pct >= 3.0 else "⏱️ 同步博弈"
                        )
                        decision_str = str(new_vals[8]) if len(new_vals) > 8 and new_vals[8] not in ("", "--") else (
                            f"👑 挂单 {price_str}元" if pct >= 7.0 else f"🔥 均线低吸 {price_str}元"
                        )

                        new_vals[3] = f"{pct:.2f}"
                        new_vals[4] = price_str
                        new_vals[5] = ladder_role
                        new_vals[6] = bid_p_str
                        new_vals[7] = pioneer_str
                        new_vals[8] = decision_str
                        new_vals[9] = f"{dff2:.1f}"
                        new_vals[10] = f"{dff3:.1f}"
                        new_vals[11] = str(rank)

                        # 更新自定义追加列
                        for ei, ec in enumerate(_extra_cols):
                            idx_in_vals = BASE_UPDATE_COUNT + ei
                            while len(new_vals) <= idx_in_vals:
                                new_vals.append("--")
                            try:
                                v = None
                                for key in (ec, ec.lower(), ec.upper()):
                                    try:
                                        v = row.get(key)
                                    except Exception:
                                        pass
                                    if v is not None:
                                        break
                                if v is None or str(v) in ('nan', 'None', ''):
                                    new_vals[idx_in_vals] = "--"
                                else:
                                    new_vals[idx_in_vals] = cct.format_col_value(ec, v)
                            except Exception:
                                pass

                        tree.item(iid, values=tuple(new_vals))

                        # 动态更新涨跌颜色 tag，并保持自选股状态
                        curr_tags = list(tree.item(iid, "tags") or [])
                        is_fav = "favorite" in curr_tags
                        tag = "flat"
                        if pct > 0:
                            tag = "up"
                        elif pct < 0:
                            tag = "down"
                        new_tags = [tag]
                        if is_fav:
                            new_tags.append("favorite")
                        tree.item(iid, tags=tuple(new_tags))
                    except Exception:
                        pass

                # 提取板块缓存（优先于 df 数据以支持离线自愈）
                block_str = getattr(self, '_block_cache', {}).get(code_str, '--')
                if block_str and block_str not in ('--', 'nan', 'None'):
                    clean_name = str(old_vals[2]).strip() if len(old_vals) > 2 else code_str
                    if clean_name.startswith("★ "):
                        clean_name = clean_name[len("★ "):]
                    all_stocks_for_stats[code_str] = {
                        "name": clean_name,
                        "percent": pct,
                        "category": block_str,
                        "close": price_str,
                        "ma5d": row.get('ma5d', 0.0) if row is not None else 0.0,
                        "ma20d": row.get('ma20d', 0.0) if row is not None else 0.0,
                        "ma60d": row.get('ma60d', 0.0) if row is not None else 0.0,
                        "rank": int(row.get('Rank', row.get('rank', 0))) if row is not None else 0,
                    }

        # 实时根据推送的行情重新分析和更新板块排行展示
        if all_stocks_for_stats:
            self.update_concept_ranking(all_stocks_for_stats)

    def load_config_settings(self):
        cfg = {
            "blk_name": "RQG.blk",
            "limit": 50,
            "interval": 5,
            "link_tdx": True,
            "link_ths": True,
            "link_vis": True,
            "sort_col": None,
            "sort_descending": False,
            "auto_refresh": False,
            "sash_ratio": 0.5,
            "column_widths": dict(getattr(self, 'DEFAULT_COLUMN_WIDTHS', {}))
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        cfg.update(loaded)
            except Exception:
                pass
        return cfg
        
    def _get_dpi_scale_factor(self):
        try:
            return self.root.winfo_fpixels('1i') / 96.0
        except Exception:
            return 1.0

    def save_sash_pos(self, event=None):
        """仅在用户手动拖拽分隔栏并释放鼠标时，更新并持久化保存 sash 比例"""
        try:
            if not hasattr(self, "paned") or self.paned is None:
                return
            pos = self.paned.sash_coord(0)[0]
            if pos <= 50:
                return
            width = self.paned.winfo_width()
            if width > 100 and pos < width - 50:
                ratio = float(pos) / float(width)
                if 0.15 <= ratio <= 0.85:
                    self.config["sash_ratio"] = ratio
                    self._last_paned_width = width
                    self.sash_restored = True
                    self.save_config_settings()
                    service_logger.debug(f"[sash] 用户拖动调整并保存 sash_ratio={ratio:.4f}")
        except Exception as e:
            service_logger.error(f"Failed to save sash position: {e}")

    def restore_sash(self, event=None, force=False):
        """恢复 PanedWindow 中间分隔栏 (sash) 的持久化比例"""
        try:
            if not hasattr(self, "paned") or self.paned is None:
                return
            width = self.paned.winfo_width()
            if width > 100:  # 确保已经分配合理的大小
                last_w = getattr(self, '_last_paned_width', 0)
                if force or not getattr(self, 'sash_restored', False) or abs(width - last_w) >= 2:
                    self._last_paned_width = width
                    ratio = self.config.get("sash_ratio", 0.5)
                    if not isinstance(ratio, (int, float)) or ratio < 0.15 or ratio > 0.85:
                        ratio = 0.5
                    target_sash = int(width * ratio)
                    self.paned.sash_place(0, target_sash, 0)
                    self.sash_restored = True
        except Exception as e:
            service_logger.debug(f"Restore sash position failed: {e}")

    def reset_sash_center(self, event=None):
        """[⚖️ 核心功能] 一键将中间垂直分隔栏精准调整到 50% 绝对居中位置并恢复黄金列宽"""
        try:
            if not hasattr(self, "paned") or self.paned is None:
                return
            self.config["sash_ratio"] = 0.5
            self.config["column_widths"] = dict(self.DEFAULT_COLUMN_WIDTHS)
            
            width = self.paned.winfo_width()
            if width > 100:
                target_sash = int(width * 0.5)
                self.paned.sash_place(0, target_sash, 0)
            self.sash_restored = True

            # 触发所有子表格重新应用黄金列宽
            all_trees = [t for t in (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res) if t and t.winfo_exists()]
            for tree in all_trees:
                for col in tree.cget("columns"):
                    def_w = self.DEFAULT_COLUMN_WIDTHS.get(col, 48)
                    min_w = self.MIN_COLUMN_WIDTHS.get(col, 35)
                    is_stretch = col in ("ladder", "bid_p", "pioneer", "decision")
                    try:
                        tree.column(col, width=def_w, minwidth=min_w, stretch=is_stretch)
                    except Exception:
                        pass

            self.save_config_settings()

            if hasattr(self, 'lbl_status'):
                self.lbl_status.config(text="✅ 垂直分隔栏与列宽已精准恢复 50% 居中", fg="#2e7d32")
            service_logger.info("垂直分隔栏与列宽已自动恢复 50% 绝对居中")
        except Exception as e:
            service_logger.error(f"Reset sash center failed: {e}")

    def save_config_settings(self):
        try:
            if hasattr(self, "entry_blk_name") and self.entry_blk_name:
                self.config["blk_name"] = self.entry_blk_name.get().strip() or "RQG.blk"
            if hasattr(self, "entry_limit") and self.entry_limit:
                try: self.config["limit"] = int(self.entry_limit.get() or "50")
                except Exception: pass
            if hasattr(self, "entry_interval") and self.entry_interval:
                try: self.config["interval"] = float(self.entry_interval.get() or "5")
                except Exception: pass
            if hasattr(self, "link_tdx_var") and self.link_tdx_var:
                self.config["link_tdx"] = self.link_tdx_var.get()
            if hasattr(self, "link_ths_var") and self.link_ths_var:
                self.config["link_ths"] = self.link_ths_var.get()
            if hasattr(self, "link_vis_var") and self.link_vis_var:
                self.config["link_vis"] = self.link_vis_var.get()
            self.config["auto_refresh"] = bool(getattr(self, "is_running", False))
            
            # 保存窗口位置与大小（防极窄尺寸污染落盘）
            if hasattr(self, "root") and self.root:
                try:
                    geo = self.root.winfo_geometry()
                    self.config["geometry"] = geo
                except Exception:
                    pass
            
            # 保存排序状态
            if hasattr(self, "tree_res") and self.tree_res is not None:
                try:
                    self.config["sort_col"] = getattr(self.tree_res, "sort_col", None)
                    self.config["sort_descending"] = getattr(self.tree_res, "sort_descending", False)
                except Exception:
                    pass

            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            service_logger.error(f"保存系统配置失败: {e}")

    def load_cached_data(self):
        cache_file = os.path.join(get_app_root(), "popularity_resonance_cache.json")
        loaded_ok = False
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
                
                if em_data or ths_data or tgb_data or lh_data or resonance_results:
                    # 恢复缓存的共振代码
                    self.resonance_codes = [r['code'] for r in resonance_results]
                    # 恢复缓存的行业板块描述
                    self._block_cache = cache.get("block_cache", {})
                    
                    # 更新表格，主线程安全
                    self.update_all_tables(em_data, ths_data, lh_data, tgb_data, resonance_results, quotes)
                    self.lbl_status.config(text="自动加载缓存数据完成", fg="darkgreen")
                    loaded_ok = True
            except Exception as e:
                service_logger.error(f"加载缓存失败: {e}")
                self.lbl_status.config(text=f"加载缓存失败: {e}", fg="red")

        # 兜底自愈：如果 cache 载入失败或无有效数据，自动加载 datacsv 目录下最近一日的持久化文件
        if not loaded_ok:
            try:
                csv_dir = os.path.join(get_app_root(), "datacsv")
                if os.path.exists(csv_dir):
                    import re
                    pattern = re.compile(r"popularity_resonance_(\d{4}-\d{2}-\d{2})\.csv(?:\.gz)?")
                    dates = []
                    for filename in os.listdir(csv_dir):
                        m = pattern.match(filename)
                        if m:
                            dates.append(m.group(1))
                    if dates:
                        dates.sort(reverse=True)
                        latest_date = dates[0]
                        service_logger.info(f"本地缓存为空，自动兜底加载最近一日历史数据: {latest_date}")
                        if self.load_history_by_date(latest_date):
                            if hasattr(self, "date_entry") and self.date_entry:
                                self.date_entry.delete(0, tk.END)
                                self.date_entry.insert(0, latest_date)
                            self.lbl_status.config(text=f"已自动兜底加载历史数据: {latest_date}", fg="darkgreen")
            except Exception as auto_err:
                service_logger.error(f"启动自动兜底加载最新历史数据失败: {auto_err}")

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
        
        # [NEW] 顶部的历史过滤公式条 (History Filter Frame)
        self.filter_frame = tk.Frame(self.root)
        self.filter_frame.pack(side="top", fill="x", padx=4, pady=2)
        
        lbl_grp = tk.Label(self.filter_frame, text="历史组:", font=("Microsoft YaHei", 9, "bold"))
        lbl_grp.pack(side="left", padx=(2, 4))
        
        self.history_selector = ttk.Combobox(
            self.filter_frame,
            values=["history1", "history2", "history3", "history4", "history5"],
            state="readonly",
            width=9
        )
        self.history_selector.pack(side="left", padx=2)
        self.history_selector.bind("<<ComboboxSelected>>", self._on_history_group_changed)
        
        # 添加 Hit 按钮
        self.btn_hit = tk.Button(
            self.filter_frame,
            text="Hit",
            command=self.calculate_history_hits_ui,
            font=("Microsoft YaHei", 8, "bold"),
            bg="#fff9c4",
            padx=2,
            pady=0
        )
        self.btn_hit.pack(side="left", padx=(6, 2))
        
        lbl_flt = tk.Label(self.filter_frame, text="过滤:", font=("Microsoft YaHei", 9, "bold"))
        lbl_flt.pack(side="left", padx=(10, 4))
        
        self.query_var = tk.StringVar()
        self.query_combo = ttk.Combobox(
            self.filter_frame,
            textvariable=self.query_var,
            width=30
        )
        self.query_combo.pack(side="left", padx=2, fill="x", expand=True)
        self.query_combo.bind("<Return>", lambda e: self.apply_filter())
        self.query_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())
        
        # 添加 🧬 DNA审计 按钮
        self.btn_query_dna = tk.Button(
            self.filter_frame,
            text="🧬 DNA审计",
            command=self.on_toolbar_dna_click,
            font=("Microsoft YaHei", 9, "bold"),
            bg="#e3f2fd",
            fg="#0d47a1",
            padx=4,
            pady=0
        )
        self.btn_query_dna.pack(side="left", padx=(10, 2))
        
        self.btn_query_exec = ttk.Button(self.filter_frame, text="过滤", command=self.apply_filter, width=6)
        self.btn_query_exec.pack(side="left", padx=2)
        
        self.btn_query_clear = ttk.Button(self.filter_frame, text="清空", command=self.clear_filter, width=6)
        self.btn_query_clear.pack(side="left", padx=2)
        
        self.btn_query_manage = ttk.Button(self.filter_frame, text="管理", command=self.manage_history, width=6)
        self.btn_query_manage.pack(side="left", padx=2)

        # 顶部的概念显示与控制栏
        self.top_concept_frame = tk.Frame(self.root)
        self.top_concept_frame.pack(side="top", fill="x", padx=4, pady=2)

        # 左侧概念文本显示容器 Frame
        self.concept_wrapper_frame = tk.Frame(self.top_concept_frame)
        self.concept_wrapper_frame.pack(side="left", fill="both", expand=True, padx=4)

        # 引导词 "当前概念:" Label (点击可打开概念板块统计详情窗口)
        self.lbl_category_title = tk.Label(
            self.concept_wrapper_frame,
            text="当前概念:",
            font=("Microsoft YaHei", 9, "bold"),
            fg="green",
            bg=self.root.cget('bg'),
            cursor="hand2"
        )
        self.lbl_category_title.pack(side="left", padx=(0, 4))
        self.lbl_category_title.bind("<Button-1>", lambda e: self.show_concept_detail_window())

        # 动态容纳各板块概念的容器 Frame
        self.dynamic_concepts_frame = tk.Frame(self.concept_wrapper_frame)
        self.dynamic_concepts_frame.pack(side="left", fill="both", expand=True)

        # 初始化时默认显示暂无板块数据
        self.lbl_empty_concept = tk.Label(
            self.dynamic_concepts_frame,
            text="暂无板块数据",
            font=("Microsoft YaHei", 9, "bold"),
            fg="gray"
        )
        self.lbl_empty_concept.pack(side="left")

        # 右侧小按钮控制容器
        self.control_buttons_frame = tk.Frame(self.top_concept_frame)
        self.control_buttons_frame.pack(side="right", fill="y")

        # 查询刷新按钮（移到顶部右侧）
        self.btn_refresh = tk.Button(
            self.control_buttons_frame,
            text="查询刷新",
            font=("Microsoft YaHei", 9, "bold", "underline"),
            fg="#E02020",
            activeforeground="#A01010",
            bg=self.root.cget('bg'),
            relief="flat",
            cursor="hand2",
            command=self.run_once_async
        )
        self.btn_refresh.pack(side="left", padx=4)

        # 写入板块按钮（移到顶部右侧）
        self.btn_write = tk.Button(
            self.control_buttons_frame,
            text="写入板块",
            font=("Microsoft YaHei", 9, "bold", "underline"),
            fg="#E02020",
            activeforeground="#A01010",
            bg=self.root.cget('bg'),
            relief="flat",
            cursor="hand2",
            command=self.write_block_async
        )
        self.btn_write.pack(side="left", padx=4)

        # 交易日志按钮（移到顶部右侧）
        self.btn_trade_log = tk.Button(
            self.control_buttons_frame,
            text="📋 交易日志",
            font=("Microsoft YaHei", 9, "bold"),
            fg="#0d47a1",
            bg="#e3f2fd",
            relief="flat",
            cursor="hand2",
            command=self.show_trade_log_window
        )
        self.btn_trade_log.pack(side="left", padx=4)

        # ⚖️ 垂直分隔栏一键居中按钮
        self.btn_center_sash = tk.Button(
            self.control_buttons_frame,
            text="⚖️ 居中",
            font=("Microsoft YaHei", 9, "bold"),
            fg="#2e7d32",
            bg="#e8f5e9",
            relief="flat",
            cursor="hand2",
            command=self.reset_sash_center
        )
        self.btn_center_sash.pack(side="left", padx=4)

        # 主显示区域 (左右分栏)
        main_pane = tk.Frame(self.root)
        main_pane.pack(fill="both", expand=True, padx=4, pady=2)

        # 引入中间垂直分隔的手动拖动
        self.paned = tk.PanedWindow(main_pane, orient="horizontal", sashrelief="raised", sashwidth=4, opaqueresize=True)
        self.paned.pack(fill="both", expand=True)

        self.sash_restored = False
        self._last_paned_width = 0

        # 左分栏
        self.left_frame = tk.Frame(self.paned)
        self.paned.add(self.left_frame, minsize=100, stretch="always")

        # 东 (EastMoney) Table Frame (1px 窄边框模式)
        self.em_container = tk.Frame(self.left_frame, bg="white", highlightbackground="#CCCCCC", highlightthickness=1, bd=0)
        self.tree_em = self.create_treeview(self.em_container, "东")

        # 左侧横向分隔栏
        self.left_sep = ttk.Separator(self.left_frame, orient="horizontal")

        # 花 (Ths) Table Frame (1px 窄边框模式)
        self.ths_container = tk.Frame(self.left_frame, bg="white", highlightbackground="#CCCCCC", highlightthickness=1, bd=0)
        self.tree_ths = self.create_treeview(self.ths_container, "花")

        # 右分栏
        self.right_frame = tk.Frame(self.paned)
        self.paned.add(self.right_frame, minsize=100, stretch="always")

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

        # 绑定 sash 的位置恢复、保存与双击一键居中
        self.paned.bind("<Configure>", lambda e: self.restore_sash(e))
        self.paned.bind("<ButtonRelease-1>", self.save_sash_pos)
        self.paned.bind("<Double-Button-1>", lambda e: self.reset_sash_center())

        # 多阶段连环延时，确保冷启动、加载配置、最大化及渲染完毕后 100% 自动装载和恢复 sash
        for delay_ms in (50, 150, 300, 500, 800, 1200):
            self.root.after(delay_ms, lambda: self.restore_sash(force=True))

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

        self.btn_history = ttk.Button(settings_frame, text="历史数据", command=self.open_history_data)
        self.btn_history.pack(side="left", padx=5)

        # 日期控制区组件，自适应自建日历选择与导航
        date_frame = tk.Frame(settings_frame)
        date_frame.pack(side="left", padx=5)
        
        tk.Label(date_frame, text="日期:").pack(side="left", padx=2)
        
        if HAS_CALENDAR:
            self.date_entry = DateEntry(date_frame, width=12, background='darkblue', 
                                      foreground='white', borderwidth=2, 
                                      date_pattern='yyyy-mm-dd',
                                      state='readonly')
            try:
                self.date_entry.set_date(datetime.strptime(self.current_date, "%Y-%m-%d"))
            except Exception:
                self.date_entry.set_date(datetime.now())
            self.date_entry.pack(side="left", padx=2)
            
            # 动态覆写 drop_down 以强行实现自动上拉展示 (防止在底部被屏幕/窗口边缘遮挡)
            def forced_up_drop_down(entry_self=self.date_entry):
                try:
                    type(entry_self).drop_down(entry_self)
                    top_cal = getattr(entry_self, '_top_cal', None)
                    if top_cal and top_cal.winfo_exists():
                        top_cal.update_idletasks()
                        x = entry_self.winfo_rootx()
                        y = entry_self.winfo_rooty()
                        cal_h = top_cal.winfo_reqheight()
                        # 向上拉起：新 y 坐标 = 输入框 Y 坐标 - 日历高度 - 2
                        new_y = y - cal_h - 2
                        top_cal.geometry(f"+{x}+{new_y}")
                except Exception as e:
                    service_logger.debug(f"日历自动上拉失败: {e}")
            
            self.date_entry.drop_down = forced_up_drop_down
            
            self.date_entry.bind("<<DateEntrySelected>>", self.on_date_changed)
            # 点击任何区域均可激活下拉日历
            self.date_entry.bind("<Button-1>", lambda e: self._show_calendar(), add="+")
            # 延时绘制日历已存历史高亮
            self.root.after(500, self._refresh_calendar_highlights)
        else:
            self.date_var = tk.StringVar(value=self.current_date)
            self.date_tk_entry = tk.Entry(date_frame, textvariable=self.date_var, width=11)
            self.date_tk_entry.pack(side="left", padx=2)
            tk.Button(date_frame, text="Go", command=self.on_date_changed, width=3).pack(side="left")

        # 快速微调天数前进后退
        tk.Button(date_frame, text="◀", command=lambda: self.shift_date(-1), width=2).pack(side="left", padx=1)
        tk.Button(date_frame, text="▶", command=lambda: self.shift_date(1), width=2).pack(side="left", padx=1)

        self.lbl_status = tk.Label(settings_frame, text="就绪", fg="blue", font=("Microsoft YaHei", 9, "bold"))
        self.lbl_status.pack(side="right", padx=10)

        # 绑定 Alt+C 全局一键挂单快捷键 (已彻底取消空格触发，仅保留 Alt+C)
        self.root.bind("<Alt-c>", self.on_quick_order)
        self.root.bind("<Alt-C>", self.on_quick_order)

    # ── 固定基础列（包含天梯梯队、买压/封单、逆势偏离、挂单决策等核心实战决策列）──
    _BASE_FIXED_COLS = ("idx", "code", "name", "val", "price", "ladder", "bid_p", "pioneer", "decision", "dff2", "dff3", "rank")
    _BASE_HEADERS = {
        "idx":      "",            # 由 first_col_title 动态填充
        "code":     "代码",
        "name":     "名称",
        "val":      "涨",          # 花标签时改为"涨幅"
        "price":    "最新",
        "ladder":   "天梯梯队",
        "bid_p":    "买压/封单",
        "pioneer":  "逆势偏离",
        "decision": "挂单决策",
        "dff2":     "dff2",
        "dff3":     "dff3",
        "rank":     "Rank",
    }

    def _get_all_cols(self):
        """返回 (all_cols, display_cols, extra_cols) 三元组，支持 cct.popularity_col 追加"""
        extra = []
        try:
            cfg_cols = getattr(cct, 'popularity_col', []) or []
            seen = set(self._BASE_FIXED_COLS)
            for c in cfg_cols:
                c = str(c).strip()
                if c and c not in seen:
                    extra.append(c)
                    seen.add(c)
        except Exception:
            pass
        all_cols = self._BASE_FIXED_COLS + tuple(extra)
        display_cols = all_cols  # 所有列均显示
        return all_cols, display_cols, extra

    def _reconfigure_tree_columns(self, tree, first_col_title, extra_cols):
        # 1. 组合所有列
        all_cols = self._BASE_FIXED_COLS + tuple(extra_cols)
        
        # 2. 重新配置 tree 的 columns
        tree.configure(columns=all_cols, displaycolumns=all_cols)
        
        # 3. 重新设置固定表头和宽度
        tree.heading("idx",      text=first_col_title)
        tree.heading("code",     text="代码")
        tree.heading("name",     text="名称")
        tree.heading("val",      text="涨幅" if first_col_title == "花" else "涨")
        tree.heading("price",    text="最新")
        tree.heading("ladder",   text="天梯梯队")
        tree.heading("bid_p",    text="买压/封单")
        tree.heading("pioneer",  text="逆势偏离")
        tree.heading("decision", text="挂单决策")
        tree.heading("dff2",     text="dff2")
        tree.heading("dff3",     text="dff3")
        tree.heading("rank",     text="Rank")
        
        saved_widths = self.config.get("column_widths", {})
        for c in self._BASE_FIXED_COLS:
            def_w = self.DEFAULT_COLUMN_WIDTHS.get(c, 48)
            min_w = self.MIN_COLUMN_WIDTHS.get(c, 35)
            w = saved_widths.get(c, def_w)
            if w < min_w:
                w = def_w
            is_stretch = c in ("ladder", "bid_p", "pioneer", "decision")
            tree.column(c, width=w, minwidth=min_w, anchor="center", stretch=is_stretch)
        
        # 4. 设置动态列的表头与宽度，并绑定点击排序
        for ec in extra_cols:
            tree.heading(ec, text=ec, command=lambda c=ec, t=tree: self.sort_column(t, c, False))
            def_w = self.DEFAULT_COLUMN_WIDTHS.get(ec, 48)
            min_w = self.MIN_COLUMN_WIDTHS.get(ec, 35)
            w = saved_widths.get(ec, def_w)
            if w < min_w:
                w = def_w
            tree.column(ec, width=w, minwidth=min_w, anchor="center", stretch=True)
            
        # 同时基础列也需要重新绑定排序
        for c in self._BASE_FIXED_COLS:
            tree.heading(c, command=lambda col=c, t=tree: self.sort_column(t, col, False))

    def create_treeview(self, parent, first_col_title):
        all_cols, display_cols, extra_cols = self._get_all_cols()

        tree = ttk.Treeview(
            parent,
            columns=all_cols,
            displaycolumns=display_cols,
            show="headings",
            selectmode="browse"
        )
        # 基础列表头
        tree.heading("idx",      text=first_col_title)
        tree.heading("code",     text="代码")
        tree.heading("name",     text="名称")
        tree.heading("val",      text="涨幅" if first_col_title == "花" else "涨")
        tree.heading("price",    text="最新")
        tree.heading("ladder",   text="天梯梯队")
        tree.heading("bid_p",    text="买压/封单")
        tree.heading("pioneer",  text="逆势偏离")
        tree.heading("decision", text="挂单决策")
        tree.heading("dff2",     text="dff2")
        tree.heading("dff3",     text="dff3")
        tree.heading("rank",     text="Rank")

        # 统一读取持久化列宽（异常过小则自动清洗恢复为黄金默认值）
        saved_widths = self.config.get("column_widths", {})
        for col in all_cols:
            def_w = self.DEFAULT_COLUMN_WIDTHS.get(col, 48)
            min_w = self.MIN_COLUMN_WIDTHS.get(col, 35)
            w = saved_widths.get(col, def_w)
            if w < min_w:
                w = def_w
            is_stretch = col in ("ladder", "bid_p", "pioneer", "decision") or col in extra_cols
            tree.column(col, width=w, minwidth=min_w, anchor="center", stretch=is_stretch)

        # 追加自定义列的表头
        for ec in extra_cols:
            tree.heading(ec, text=ec)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview,
                                  style="Slim.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 颜色标签
        tree.tag_configure("up",       foreground="#E02020", font=("Microsoft YaHei", 9, "bold"))
        tree.tag_configure("down",     foreground="#20A020", font=("Microsoft YaHei", 9, "bold"))
        tree.tag_configure("flat",     foreground="#000000", font=("Microsoft YaHei", 9))
        tree.tag_configure("favorite", background="#e6ffe6", font=("Microsoft YaHei", 9, "bold"))

        # 绑定点击表头排序
        for col in all_cols:
            tree.heading(col, command=lambda c=col, t=tree: self.sort_column(t, c, False))

        tree.sort_col = self.config.get("sort_col", None)
        tree.sort_descending = self.config.get("sort_descending", False)

        # 绑定联动与双击事件
        tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        tree.bind("<Button-3>", self.show_context_menu)
        tree.bind("<Double-1>", self.on_tree_double_click)
        tree.bind("<Control-c>", self.on_copy_shortcut)
        tree.bind("<Alt-c>", self.on_quick_order)
        tree.bind("<Alt-C>", self.on_quick_order)
        # 绑定拖动表头分隔线调整列宽后的多表格同步与统一持久化
        tree.bind("<ButtonRelease-1>", lambda e, t=tree: self._on_tree_column_drag_release(e, t), add="+")

        return tree

    def sort_column(self, tree, col, reverse, auto_restore=False):
        # 1. 提取数据项并转化为可排序的值
        l = []
        for k in tree.get_children(''):
            try:
                val = tree.set(k, col)
            except Exception:
                # 若当前 tree 没有该列，直接安全退出，防御 Invalid column index 异常
                return
            code = str(tree.set(k, "code")).strip().zfill(6)
            l.append((val, code, k))
            
        def try_convert(val):
            if val is None:
                return (0, -9999.0)
            val_str = str(val).strip().replace('%', '')
            if not val_str or val_str == '--':
                return (0, -9999.0)
            try:
                return (0, float(val_str))
            except ValueError:
                return (1, val_str.lower())
                
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()

        def sort_key(item):
            val, code, k = item
            is_fav_bool = code in fav_stocks
            if reverse:
                fav_part = 1 if is_fav_bool else 0
            else:
                fav_part = 0 if is_fav_bool else 1
            return (fav_part, try_convert(val))
            
        # 2. 稳定原地排序
        l.sort(key=sort_key, reverse=reverse)
        
        # 3. 重新插入视图
        for index, (val, code, k) in enumerate(l):
            tree.move(k, '', index)
            
        # 4. 保存排序状态
        tree.sort_col = col
        tree.sort_descending = reverse
        
        if not auto_restore:
            # 手动点击时更新该列 heading，以便下次反转方向
            tree.heading(col, command=lambda: self.sort_column(tree, col, not reverse))
            
            all_trees = (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res)
            # 只有当当前排行的 tree 本身属于主表时，才广播同步给其他主表
            if tree in all_trees:
                for other_tree in all_trees:
                    if other_tree != tree:
                        self.sort_column(other_tree, col, reverse, auto_restore=True)
            
            # 同步排序到已打开的板块个股列表窗口（如果有同样的 col 或可映射的 col）
            if getattr(self, "concept_win", None) is not None:
                try:
                    if self.concept_win.winfo_exists() and getattr(self, "concept_tree", None) is not None:
                        concept_cols = self.concept_tree["columns"]
                        target_col = col
                        if target_col in concept_cols:
                            self.sort_column(self.concept_tree, target_col, reverse, auto_restore=True)
                except Exception as sync_err:
                    service_logger.debug(f"同步概念个股窗口排序异常: {sync_err}")

            # 同步刷新概念板块统计详情窗口的排序
            if getattr(self, "_concept_win", None) is not None:
                try:
                    if self._concept_win.winfo_exists():
                        self.update_concept_detail_content()
                except Exception as detail_err:
                    service_logger.debug(f"同步刷新概念详情窗口异常: {detail_err}")

            # [OPTIMIZE] 排序时仅在内存中更新状态，不执行写盘。退出关闭时统一持久化。
            
        # 5. 更新表头的 ▲/▼ 指示器
        self.update_header_arrows(tree, col, reverse)

    def update_header_arrows(self, tree, active_col, reverse):
        # 1. 尝试获取 tree 的实际 columns 元组，如果抛错则说明 tree 无效
        try:
            tree_cols = tree["columns"]
        except Exception:
            return

        # 2. 探测当前 Tree 绑定的 first_col_title 基础名称
        first_title = "东"
        all_trees = (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res)
        if tree in all_trees:
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

            base_headers = dict(self._BASE_HEADERS)
            base_headers["idx"] = first_title
            base_headers["val"] = "涨幅" if first_title == "花" else "涨"
            # 补充自定义列（列名即显示文字）
            _, _, extra_cols = self._get_all_cols()
            for ec in extra_cols:
                base_headers[ec] = ec

            all_display = self._BASE_FIXED_COLS + tuple(extra_cols)
            for col in all_display:
                base_text = base_headers.get(col, col)
                if col == active_col:
                    arrow = " ↓" if reverse else " ↑"
                    try:
                        tree.heading(col, text=f"{base_text}{arrow}")
                    except Exception:
                        pass
                else:
                    try:
                        tree.heading(col, text=base_text)
                    except Exception:
                        pass
        else:
            # 如果是其他 Treeview (例如个股列表)，使用通用表头字典
            col_texts = {
                "idx": "序号",
                "code": "代码",
                "name": "名称",
                "val": "涨幅(%)",
                "price": "最新",
                "dff2": "dff2",
                "dff3": "dff3",
                "rank": "Rank",
                "percent": "涨幅(%)",
                "dff": "dff",
                "volume": "成交量",
                "red": "连阳",
                "win": "主升"
            }
            # 补充自定义列
            _, _, extra_cols = self._get_all_cols()
            for ec in extra_cols:
                col_texts[ec] = ec

            for col in tree_cols:
                base_text = col_texts.get(col, col)
                if col == active_col:
                    arrow = " ↓" if reverse else " ↑"
                    try:
                        tree.heading(col, text=f"{base_text}{arrow}")
                    except Exception:
                        pass
                else:
                    try:
                        tree.heading(col, text=base_text)
                    except Exception:
                        pass


    def tree_scroll_to_code(self, code, select_win=False, vis=True):
        """
        [NEW] 跨视图联动与自动滚动定位指定股票代码行 (Thread-Safe + Anti-recursion)
        在当前主界面的所有视图 (东、花、开、淘、合) 以及板块个股弹窗中搜索 code，
        如果存在则自动选中、聚焦并滚动到该行 (see)，并联动 TDX/THS/可视化器。
        """
        if not code:
            return False
        code = str(code).strip().zfill(6)

        # 记录当前选中的 code，防止事件循环与重复触发
        self._active_link_code = code

        # 1. 触发外部物理通道联动 (TDX/THS/可视化器) - 全部放入后台守护线程，避免 Windows IPC / Socket 阻塞主线程
        if vis:
            def _bg_link(c):
                try:
                    is_tdx = self.link_tdx_var.get()
                    is_ths = self.link_ths_var.get()
                    if is_tdx or is_ths:
                        flags = {'tdx': is_tdx, 'ths': is_ths, 'dfcf': False}
                        if get_link_manager:
                            get_link_manager().push(c, flags=flags)
                        elif self.local_sender:
                            self.local_sender.send(c)
                    if self.link_vis_var.get():
                        self.send_to_visualizer(c)
                except Exception as ex:
                    service_logger.debug(f"联动发送异常: {ex}")

            threading.Thread(target=_bg_link, args=(code,), daemon=True).start()

            if hasattr(self, 'lbl_status'):
                try:
                    curr_txt = self.lbl_status.cget("text")
                    if "【决策推演" in curr_txt:
                        if "(已联动)" not in curr_txt and "已联动" not in curr_txt:
                            self.lbl_status.config(text=curr_txt.replace("【决策推演】", "【决策推演·已联动】"), fg="#b30000")
                    else:
                        self.lbl_status.config(text=f"已联动定位: {code}", fg="darkgreen")
                except Exception:
                    pass

        # 2. UI 视图滚动定位
        def _do_scroll():
            if getattr(self, '_is_scrolling_to_code', False):
                return
            self._is_scrolling_to_code = True
            try:
                # 收集所有当前活跃的 Treeview
                target_trees = [self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res]
                concept_tree = getattr(self, 'concept_tree', None)
                if concept_tree and concept_tree.winfo_exists():
                    target_trees.append(concept_tree)

                for tree in target_trees:
                    if not tree or not tree.winfo_exists():
                        continue
                    cols = list(tree["columns"])
                    code_idx = cols.index("code") if "code" in cols else 1
                    for iid in tree.get_children():
                        vals = tree.item(iid, "values")
                        if vals and len(vals) > code_idx:
                            c = str(vals[code_idx]).strip().zfill(6)
                            if c == code:
                                curr_sel = tree.selection()
                                if not curr_sel or curr_sel[0] != iid:
                                    tree.selection_set(iid)
                                tree.focus(iid)
                                tree.see(iid)
                                break
            except Exception as e:
                service_logger.debug(f"tree_scroll_to_code 滚动异常: {e}")
            finally:
                self._is_scrolling_to_code = False

        if threading.current_thread() is threading.main_thread():
            _do_scroll()
        else:
            self.root.after(0, _do_scroll)
        return True

    def on_tree_select(self, event):
        if getattr(self, '_is_scrolling_to_code', False):
            return
        tree = event.widget
        self._last_active_tree = tree
        selection = tree.selection()
        if selection:
            item = tree.item(selection[0])
            values = item.get("values")
            if values and len(values) >= 2:
                cols = list(tree["columns"])
                code_idx = cols.index("code") if "code" in cols else 1
                name_idx = cols.index("name") if "name" in cols else 2
                ladder_idx = cols.index("ladder") if "ladder" in cols else 5
                bid_idx = cols.index("bid_p") if "bid_p" in cols else 6
                pio_idx = cols.index("pioneer") if "pioneer" in cols else 7
                dec_idx = cols.index("decision") if "decision" in cols else 8

                if len(values) > code_idx:
                    code = str(values[code_idx]).strip().zfill(6)
                    name = str(values[name_idx]).strip().replace("★ ", "") if len(values) > name_idx else code
                    ladder_str = str(values[ladder_idx]) if len(values) > ladder_idx else ""
                    bid_str = str(values[bid_idx]) if len(values) > bid_idx else "买压 80%"
                    pio_str = str(values[pio_idx]) if len(values) > pio_idx else ""
                    dec_str = str(values[dec_idx]) if len(values) > dec_idx else ""

                    info_parts = [f"【决策推演】{code} {name}"]
                    if ladder_str and ladder_str not in ("--", ""):
                        info_parts.append(ladder_str)
                    if bid_str and bid_str not in ("--", ""):
                        info_parts.append(bid_str)
                    if pio_str and pio_str not in ("--", "", "⏱️ 同步博弈"):
                        info_parts.append(pio_str)
                    if dec_str and dec_str not in ("--", ""):
                        info_parts.append(dec_str)
                    info_parts.append("[按Alt+C一键挂单]")

                    status_msg = " | ".join(info_parts)
                    if hasattr(self, 'lbl_status'):
                        self.lbl_status.config(text=status_msg, fg="#b30000")

                    # 💥 关键防重入：如果当前 code 已经处于 active 状态，则说明是程序选中的，不重复触发广播
                    if getattr(self, '_active_link_code', None) == code:
                        return
                    self.tree_scroll_to_code(code, vis=True)

    def on_quick_order(self, event=None):
        """[🚀 核心实战] 键盘 Alt+C / 闪电买入 一键直连通达信交易终端与精准填单"""
        target_tree = None
        selection = []

        # 优先级 1: 当前获得焦点的控件如果是 Treeview
        try:
            focused = self.root.focus_get()
            if isinstance(focused, ttk.Treeview):
                sel = focused.selection()
                if sel:
                    target_tree = focused
                    selection = sel
        except Exception:
            pass

        # 优先级 2: 上次激活的表格
        if not selection:
            tree_candidate = getattr(self, '_last_active_tree', None)
            if tree_candidate and tree_candidate.winfo_exists():
                sel = tree_candidate.selection()
                if sel:
                    target_tree = tree_candidate
                    selection = sel

        # 优先级 3: 遍历所有子表格查找有选中的行
        if not selection:
            for t in (self.tree_res, self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb):
                if t and t.winfo_exists():
                    sel = t.selection()
                    if sel:
                        target_tree = t
                        selection = sel
                        break

        # 优先级 4: 如果都没有选中，默认选中第 1 个有数据的表格的第 1 行
        if not selection:
            for t in (self.tree_res, self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb):
                if t and t.winfo_exists():
                    children = t.get_children()
                    if children:
                        target_tree = t
                        selection = [children[0]]
                        t.selection_set(children[0])
                        t.focus(children[0])
                        break

        if not target_tree or not selection:
            if hasattr(self, 'lbl_status'):
                self.lbl_status.config(text="⚠️ 暂无可操作的股票标的，请先查询刷新！", fg="orange")
            return "break"

        item = target_tree.item(selection[0])
        values = item.get("values")
        if not values or len(values) < 2:
            return "break"

        cols = list(target_tree["columns"])
        code_idx = cols.index("code") if "code" in cols else 1
        name_idx = cols.index("name") if "name" in cols else 2
        price_idx = cols.index("price") if "price" in cols else 4
        ladder_idx = cols.index("ladder") if "ladder" in cols else 5
        dec_idx = cols.index("decision") if "decision" in cols else 8

        code = str(values[code_idx]).strip().zfill(6)
        name = str(values[name_idx]).strip().replace("★ ", "") if len(values) > name_idx else code
        price_str = str(values[price_idx]) if len(values) > price_idx else "--"
        ladder_str = str(values[ladder_idx]) if len(values) > ladder_idx else "人气真龙"
        dec_str = str(values[dec_idx]) if len(values) > dec_idx else ""

        try:
            target_p = float(price_str)
        except Exception:
            target_p = 0.0

        # 如果当前现价无效，尝试从挂单决策文本中提取数字价格（如 '👑 挂单 15.74元'）
        if target_p <= 0 and dec_str:
            import re
            m = re.search(r'(\d+\.?\d*)\s*元', dec_str)
            if m:
                try:
                    target_p = float(m.group(1))
                except Exception:
                    pass

        try:
            from popularity_resonance_service import QuickOrderExecutor
            executor = QuickOrderExecutor.get_instance()
            res = executor.execute_quick_buy(
                code=code,
                name=name,
                target_price=target_p,
                shares=1000,
                strategy_tag=f"👑 人气共振·{ladder_str}"
            )
            msg = res.get("msg", "一键挂单成功")
            if hasattr(self, 'lbl_status'):
                self.lbl_status.config(text=f"⚡ {msg}", fg="#ff3b30")
        except Exception as ex:
            service_logger.error(f"一键挂单执行异常: {ex}")
            if hasattr(self, 'lbl_status'):
                self.lbl_status.config(text=f"❌ 一键挂单异常: {ex}", fg="red")
        return "break"

    def show_trade_log_window(self):
        """打开今日实盘与一键挂单交易流水窗口 (支持位置持久化与表头排序)"""
        try:
            if hasattr(self, '_trade_log_win') and self._trade_log_win and self._trade_log_win.winfo_exists():
                self._trade_log_win.deiconify()
                self._trade_log_win.lift()
                self._trade_log_win.focus_force()
                if hasattr(self._trade_log_win, '_refresh_data'):
                    self._trade_log_win._refresh_data()
                return

            top = tk.Toplevel(self.root)
            self._trade_log_win = top
            top.title("📋 今日交易流水与一键挂单记录 (Trade Log)")
            
            # 恢复持久化窗口位置与尺寸
            saved_geo = self.config.get("trade_log_geometry", "880x480")
            try:
                top.geometry(saved_geo)
            except Exception:
                top.geometry("880x480")
            top.attributes("-topmost", True)

            # 顶部工具栏
            top_bar = tk.Frame(top, bg="#f5f5f5", pady=4)
            top_bar.pack(side="top", fill="x", padx=4)

            lbl_hint = tk.Label(top_bar, text="⚡ 今日实盘与一键挂单流水明细 (点击表头可多字段升降序排序)", font=("Microsoft YaHei", 9, "bold"), fg="#0d47a1", bg="#f5f5f5")
            lbl_hint.pack(side="left", padx=4)

            btn_close = tk.Button(top_bar, text="❌ 关闭 (Esc)", font=("Microsoft YaHei", 9), fg="#b71c1c", bg="#ffebee", relief="flat", cursor="hand2", command=top.destroy)
            btn_close.pack(side="right", padx=4)

            btn_ref = tk.Button(top_bar, text="🔄 刷新流水", font=("Microsoft YaHei", 9, "bold"), fg="#1b5e20", bg="#e8f5e9", relief="flat", cursor="hand2")
            btn_ref.pack(side="right", padx=4)

            # 主表格
            table_frame = tk.Frame(top)
            table_frame.pack(side="top", fill="both", expand=True, padx=4, pady=2)

            cols = ("time", "code", "name", "action", "price", "shares", "amount", "strategy")
            headers = {"time": "时间", "code": "代码", "name": "名称", "action": "方向",
                       "price": "委托价", "shares": "数量", "amount": "金额", "strategy": "策略来源"}
            
            tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
            tree.sort_col = "time"
            tree.sort_reverse = True  # 默认时间倒序

            tree.column("time", width=130, anchor="center")
            tree.column("code", width=65, anchor="center")
            tree.column("name", width=75, anchor="center")
            tree.column("action", width=55, anchor="center")
            tree.column("price", width=70, anchor="center")
            tree.column("shares", width=70, anchor="center")
            tree.column("amount", width=85, anchor="center")
            tree.column("strategy", width=220, anchor="w")

            scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            tree.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")

            def sort_trade_log(col):
                items = []
                for iid in tree.get_children():
                    val = tree.set(iid, col)
                    items.append((val, iid))

                def _convert(v):
                    v_str = str(v).strip().replace(',', '').replace('￥', '').replace('%', '').replace('+', '')
                    try:
                        return (0, float(v_str))
                    except Exception:
                        return (1, str(v).lower())

                if tree.sort_col == col:
                    tree.sort_reverse = not tree.sort_reverse
                else:
                    tree.sort_col = col
                    tree.sort_reverse = True  # 默认降序

                items.sort(key=lambda x: _convert(x[0]), reverse=tree.sort_reverse)
                for idx, (_, iid) in enumerate(items):
                    tree.move(iid, '', idx)

                for c in cols:
                    indicator = " ▼" if (c == tree.sort_col and tree.sort_reverse) else (" ▲" if (c == tree.sort_col and not tree.sort_reverse) else "")
                    tree.heading(c, text=headers.get(c, c) + indicator, command=lambda _c=c: sort_trade_log(_c))

            for c in cols:
                tree.heading(c, text=headers.get(c, c), command=lambda _c=c: sort_trade_log(_c))

            # 加载数据函数
            def load_db_data():
                tree.delete(*tree.get_children())
                try:
                    from trade_gateway import DB_FILE
                    from db_utils import SQLiteConnectionManager
                    mgr = SQLiteConnectionManager.get_instance(DB_FILE)
                    conn = mgr.get_connection()
                    cur = conn.cursor()
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS mock_trade_log (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            date TEXT, time TEXT, code TEXT, name TEXT, sector TEXT,
                            action TEXT, price REAL, shares INTEGER, amount REAL,
                            reason TEXT, strategy_tag TEXT, pnl_pct REAL DEFAULT 0.0,
                            is_simulated INTEGER DEFAULT 0
                        )
                    """)
                    conn.commit()
                    cur.execute("SELECT time, code, name, action, price, shares, amount, strategy_tag, date FROM mock_trade_log ORDER BY id DESC")
                    rows = cur.fetchall()
                    cur.close()

                    for r in rows:
                        t_str = f"{r[8]} {r[0]}" if r[8] else r[0]
                        act_str = "买入" if r[3] == "BUY" else ("卖出" if r[3] == "SELL" else str(r[3]))
                        tree.insert("", "end", values=(t_str, r[1], r[2], act_str, f"{float(r[4]):.2f}", f"{int(r[5]):,}", f"{float(r[6]):,.2f}", r[7]))
                except Exception as db_err:
                    service_logger.error(f"读取流水日志异常: {db_err}")

            top._refresh_data = load_db_data
            btn_ref.config(command=load_db_data)
            load_db_data()

            # 绑定选中行联动（鼠标单击 + 键盘上下键 ↑ / ↓ 导航）
            def on_trade_log_select(event):
                if getattr(self, '_is_scrolling_to_code', False):
                    return
                sel = tree.selection()
                if sel:
                    vals = tree.item(sel[0], "values")
                    if vals and len(vals) >= 2:
                        code = str(vals[1]).strip().zfill(6)
                        if code and code != "000000":
                            if getattr(self, '_active_link_code', None) == code:
                                return
                            self.tree_scroll_to_code(code, vis=True)

            tree.bind("<<TreeviewSelect>>", on_trade_log_select)

            # 位置持久化保存
            def on_geo_save(e=None):
                try:
                    if top.winfo_exists():
                        geo = top.geometry()
                        if geo:
                            self.config["trade_log_geometry"] = geo
                            self.save_config_settings()
                except Exception:
                    pass

            top.bind("<Escape>", lambda e: top.destroy())
            top.protocol("WM_DELETE_WINDOW", lambda: [on_geo_save(), top.destroy()])

        except Exception as ex:
            service_logger.error(f"打开交易日志窗口失败: {ex}")

    def on_tree_double_click(self, event):
        tree = event.widget
        selection = tree.selection()
        if selection:
            item = tree.item(selection[0])
            values = item.get("values")
            if values and len(values) >= 2:
                code = str(values[1]).strip().zfill(6)
                name = str(values[2]).strip() if len(values) >= 3 else code
                # 从 _block_cache 字典查询板块信息（不再依赖隐藏列）
                block = getattr(self, '_block_cache', {}).get(code, "--")
                if not block or block in ("--", "nan", "None"):
                    block = "暂无板块信息"

                # 弹出置顶提示框显示所属行业板块信息
                messagebox.showinfo("板块信息", f"个股: {name} ({code})\n所属行业板块: {block}", parent=self.root)

    def send_to_visualizer(self, code):
        IPC_HOST = '127.0.0.1'
        IPC_PORT = 26668
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect((IPC_HOST, IPC_PORT))
            
            # 检测是否处于历史数据模式 (self.current_date 与今日不同)
            today = time.strftime("%Y-%m-%d")
            view_date = getattr(self, "current_date", today)
            if view_date != today:
                payload = f"TIME_LINK|{code}|{view_date}"
            else:
                payload = f"CODE|{code}"
                
            s.send(payload.encode('utf-8'))
            s.close()
        except Exception:
            pass

    def on_code_click(self, code, date=None):
        """DNA 审计窗口点击个股时，回传人气排行界面以触发 TDX、Visualizer 联动以及高亮该个股"""
        if not code:
            return
        self.tree_scroll_to_code(code, vis=True)

    def _run_dna_audit_batch(self, code_to_name, end_date=None, resample='d'):
        from backtest_feature_auditor import audit_multiple_codes, show_dna_audit_report_window
        from tkinter import messagebox
        import threading
        
        # 🚀 防重入保护
        if getattr(self, '_dna_audit_running', False):
            return
        self._dna_audit_running = True
        
        codes = list(code_to_name.keys())
        if not codes:
            self._dna_audit_running = False
            return
            
        if not end_date:
            end_date = self.current_date.replace("-", "")
            
        # 弹一个带进度条的提示
        top = tk.Toplevel(self.root)
        top.withdraw() 
        top.attributes("-alpha", 0.0) 
        top.title("🧬 DNA 审计中...")
        
        # 界面美化
        top.configure(bg='#f8f9fa')
        content_frame = tk.Frame(top, bg='#f8f9fa', padx=15, pady=15)
        content_frame.pack(expand=True, fill='both')
        
        msg_label = tk.Label(content_frame, text=f"正在审计 {len(codes)} 只个股...", 
                            font=("微软雅黑", 9), bg='#f8f9fa', fg='#333')
        msg_label.pack(pady=(0, 10))
        
        # 进度条
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(content_frame, variable=progress_var, maximum=len(codes), mode='determinate', length=280)
        progress_bar.pack(pady=5)
        
        status_label = tk.Label(content_frame, text="初始化中...", font=("微软雅黑", 8), bg='#f8f9fa', fg='#666')
        status_label.pack()
        
        # 初始化展示位置
        w, h = 320, 140
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.attributes("-topmost", True)
        top.deiconify() 
        
        def progress_cb(curr, total, msg):
            """跨线程进度回调"""
            def _update():
                try:
                    if not top.winfo_exists(): return
                    progress_var.set(curr)
                    status_label.config(text=msg)
                    if curr >= total:
                        status_label.config(text="✅ 正在呼出报告...")
                except tk.TclError:
                    pass 
                    
            self.root.after(0, _update)
            
        def run_task():
            try:
                # 调用批量接口
                summaries = audit_multiple_codes(codes, 
                                               end_date=end_date, 
                                               code_to_name=code_to_name,
                                               progress_callback=progress_cb,
                                               resample=resample)
                # 切回主线程展示
                def _show_report():
                    if top.winfo_exists():
                        top.destroy()
                    
                    # 支持窗口复用
                    if hasattr(self, '_dna_audit_win') and self._dna_audit_win and self._dna_audit_win.winfo_exists():
                        self._dna_audit_win.update_report(summaries, end_date=end_date, resample=resample)
                    else:
                        self._dna_audit_win = show_dna_audit_report_window(summaries, parent=self, end_date=end_date, resample=resample)
                
                self.root.after(0, _show_report)
            except Exception as e:
                import traceback
                print(traceback.format_exc())
                self.root.after(0, lambda: [top.destroy() if top.winfo_exists() else None, messagebox.showerror("DNA 审计出错", str(e), parent=self.root)])
            finally:
                self._dna_audit_running = False
                
        threading.Thread(target=run_task, daemon=True).start()

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

        # 左右容器 pack 完毕后，Tkinter 几何重算可能会重置 sash 位置，延迟触发强行恢复
        if hasattr(self, 'root') and hasattr(self, 'paned'):
            self.root.after_idle(lambda: self.restore_sash(force=True))
            self.root.after(30, lambda: self.restore_sash(force=True))
            self.root.after(100, lambda: self.restore_sash(force=True))

    def clear_all_trees(self):
        for tree in (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res):
            for item in tree.get_children():
                tree.delete(item)

    def run_once_async(self):
        self.btn_refresh.config(state="disabled", text="正在查询...")
        self.lbl_status.config(text="正在获取数据...", fg="blue")
        # 手动查询刷新，传入 force_save=True 以强制持久化数据
        threading.Thread(target=self._run_once_job, args=(True,), daemon=True).start()

    def _run_once_job(self, force_save=False):
        try:
            # 💥 自动使用 IPC 动态端口同步拉取最新行情数据包，完事即刻物理释放端口
            service_logger.info("正在通过 IPC 动态端口同步请求最新行情数据...")
            self.request_dynamic_ipc_sync(timeout=8.0)

            today = time.strftime("%Y-%m-%d")
            # 💥 如果是自动刷新中或手动触发查询刷新，且跨天了，自动切换到今日日期
            if self.is_running or force_save:
                current_view_date = self.current_date
                if current_view_date != today:
                    service_logger.info(f"检测到日期已由 {current_view_date} 切换至今日 {today}，执行界面日期同步...")
                    self.current_date = today
                    self._last_realtime_today = today
                    def _update_ui_date():
                        if hasattr(self, 'date_entry'):
                            try:
                                dt_today = datetime.strptime(today, "%Y-%m-%d")
                                self.date_entry.set_date(dt_today)
                            except Exception:
                                pass
                        elif hasattr(self, 'date_var'):
                            self.date_var.set(today)
                    self.root.after(0, _update_ui_date)

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
                        "timestamp": time.time(),
                        "block_cache": getattr(self, "_block_cache", {})
                    }
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, indent=4, ensure_ascii=False)
                except Exception as cache_err:
                    service_logger.error(f"写入数据缓存失败: {cache_err}")
            
            # 每日数据持久化更新当日数据 (在 save_daily_resonance_csv 内部自适应校验交易日)
            self.save_daily_resonance_csv(em_data, ths_data, lh_data, tgb_data, resonance_results[:limit], all_quotes, force_save=force_save)
            
            today = time.strftime("%Y-%m-%d")
            current_view_date = self.current_date
            if current_view_date == today:
                self._last_realtime_today = today
                self.root.after(0, lambda: self.update_all_tables(em_data, ths_data, lh_data, tgb_data, resonance_results[:limit], all_quotes))
            else:
                service_logger.info(f"后台自动更新了今日数据，因当前正处于历史数据({current_view_date})复盘模式，跳过界面重绘。")
            
        except Exception as e:
            self.root.after(0, lambda: self.lbl_status.config(text=f"刷新失败: {e}", fg="red"))
        finally:
            self.root.after(0, lambda: self.btn_refresh.config(state="normal", text="查询刷新"))

    def update_all_tables(self, em_data, ths_data, lh_data, tgb_data, resonance_results, quotes):
        import pandas as pd
        self._last_test_df_hits = None
        # 缓存最新传入的数据，用于点击概念过滤时重新渲染
        self._last_data_cache = {
            "em_data": em_data,
            "ths_data": ths_data,
            "lh_data": lh_data,
            "tgb_data": tgb_data,
            "resonance_results": resonance_results,
            "quotes": quotes
        }

        # 实时/缓存模式重新切回实时的自定义列配置
        _, _, _extra_cols = self._get_all_cols()
        self._reconfigure_tree_columns(self.tree_em, "东", _extra_cols)
        self._reconfigure_tree_columns(self.tree_ths, "花", _extra_cols)
        self._reconfigure_tree_columns(self.tree_lh, "龙", _extra_cols)
        self._reconfigure_tree_columns(self.tree_tgb, "淘", _extra_cols)
        self._reconfigure_tree_columns(self.tree_res, "合", _extra_cols)

        self.clear_all_trees()

        # 用于统计前 10 概念热度的个股信息收集字典
        all_stocks_for_stats = {}

        # 1. 提取所有进入"合"表（共振表）的股票代码，用于在其他原始排行榜中做去重过滤
        resonance_set = {item["code"] for item in resonance_results}

        # 获取最新的行情快照 DataFrame
        df = getattr(self, "sync_manager", None)
        df_cache = df.get_current_df() if df is not None else None

        # 获取全局自选股代码集合
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()

        # 批量计算公式过滤匹配结果，彻底根治循环逐行 pd.eval 导致的几秒卡顿
        matched_codes = set()
        has_query = bool(getattr(self, 'query_expr', None))
        if has_query:
            # 收集所有涉及到的股票代码
            all_involved_codes = set()
            if em_data: all_involved_codes.update(em_data.keys())
            if ths_data: all_involved_codes.update(ths_data.keys())
            if lh_data: all_involved_codes.update(lh_data.keys())
            if tgb_data: all_involved_codes.update(tgb_data.keys())
            if resonance_results:
                all_involved_codes.update(item["code"] for item in resonance_results if "code" in item)
            
            if all_involved_codes:
                import numpy as np
                involved_list = list(all_involved_codes)
                
                # 1. 尝试从 df_cache 提取已有行
                df_parts = []
                missing_codes = []
                if df_cache is not None and not df_cache.empty:
                    existing_codes = [c for c in involved_list if c in df_cache.index]
                    missing_codes = [c for c in involved_list if c not in df_cache.index]
                    if existing_codes:
                        df_parts.append(df_cache.loc[existing_codes].copy())
                else:
                    missing_codes = involved_list
                    
                # 2. 对缺失的股票，构建基础属性的 fallback DataFrame
                if missing_codes:
                    fallback_rows = []
                    for c in missing_codes:
                        code_str = str(c).strip().zfill(6)
                        quote = quotes.get(c, {"name": "--", "percent": 0.0})
                        fallback_rows.append({
                            "code": code_str,
                            "name": quote.get("name", "--"),
                            "percent": quote.get("percent", 0.0),
                            "ratio": quote.get("percent", 0.0),
                            "price": quote.get("price", 0.0),
                            "close": quote.get("price", 0.0),
                            "trade": quote.get("price", 0.0),
                            "dff2": 0.0,
                            "dff3": 0.0,
                            "rank": 0,
                            "category": self._block_cache.get(code_str, "--"),
                            "hy": self._block_cache.get(code_str, "--"),
                        })
                    df_fallback = pd.DataFrame(fallback_rows)
                    df_fallback.set_index("code", drop=False, inplace=True)
                    df_parts.append(df_fallback)
                    
                # 3. 合并成完整的待测大宽表
                df_to_test = pd.concat(df_parts) if df_parts else pd.DataFrame()
                
                if not df_to_test.empty:
                    # 4. 自动补全可能缺失的指标列，防止 eval 抛 NameError 警告
                    try:
                         from query_engine_util import extract_columns
                         expr_cols = extract_columns(self.query_expr)
                         for col in expr_cols:
                             if col not in df_to_test.columns:
                                 if col in ('category', 'hy', 'blockname', 'name', 'block', 'details'):
                                     df_to_test[col] = ""
                                 else:
                                     df_to_test[col] = 0.0
                    except Exception:
                         pass
                    
                    # 5. 调用 query_engine.execute 一次性批量运行公式
                    try:
                        from query_engine_util import query_engine
                        res = query_engine.execute(df_to_test, self.query_expr)
                        
                        # 6. 收集匹配成功的代码集合
                        if isinstance(res, pd.DataFrame):
                            matched_codes = set(res.index.astype(str))
                        elif isinstance(res, (pd.Series, np.ndarray, list)):
                            matched_codes = set(str(x) for x in res)
                        elif isinstance(res, (bool, np.bool_)):
                            if res:
                                matched_codes = set(df_to_test.index.astype(str))
                    except Exception as e:
                        service_logger.error(f"批量过滤公式执行失败: {e}")

        # 预计算本次的自定义追加列（全局统一，所有 tree 共享同一列结构）
        # 板块信息缓存，不再存入 Treeview，双击时查询
        if not hasattr(self, "_block_cache") or self._block_cache is None:
            self._block_cache = {}

        _, _, _extra_cols = self._get_all_cols()

        def _read_extra_vals(row_obj) -> tuple:
            """从 df_cache 行中读取自定义列的值，找不到则返回 '--'"""
            if row_obj is None or not _extra_cols:
                return tuple(["--"] * len(_extra_cols))
            result = []
            for ec in _extra_cols:
                try:
                    v = None
                    for key in (ec, ec.lower(), ec.upper()):
                        try:
                            v = row_obj.get(key)
                        except Exception:
                            pass
                        if v is not None:
                            break
                    if v is None or str(v) in ('nan', 'None', ''):
                        result.append("--")
                    else:
                        result.append(cct.format_col_value(ec, v))
                except Exception:
                    result.append("--")
            return tuple(result)

        # 2. 定义带去重功能的单个表格填充辅助函数
        def populate(tree, data_dict):
            import pandas as pd
            sorted_items = sorted(
                data_dict.items(),
                key=lambda x: (0 if str(x[0]).strip().zfill(6) in fav_stocks else 1, x[1])
            )
            display_rank = 1
            for _, (code, _) in enumerate(sorted_items, 1):
                # 如果该个股已被归入共振榜，则在其他表（东、花、开、淘）中过滤去重
                if code in resonance_set:
                    continue

                quote = quotes.get(code, {"name": "--", "percent": 0.0})
                name = quote["name"]
                pct = quote["percent"]

                price_str = "--"
                dff2_str = "--"
                dff3_str = "--"
                rank_str = "--"
                block_str = "--"
                row_obj = None

                if df_cache is not None and not df_cache.empty:
                    code_str = str(code).strip().zfill(6)
                    if code_str in df_cache.index:
                        try:
                            row_obj = df_cache.loc[code_str]
                            import pandas as pd
                            if isinstance(row_obj, pd.DataFrame):
                                row_obj = row_obj.iloc[0]
                            pct = float(row_obj.get('percent', row_obj.get('ratio', pct)))
                            price_str = f"{float(row_obj.get('trade', row_obj.get('close', row_obj.get('price', 0.0)))):.2f}"
                            dff2_str = f"{float(row_obj.get('dff2', row_obj.get('DFF2', 0.0))):.1f}"
                            dff3_str = f"{float(row_obj.get('dff3', row_obj.get('DFF3', 0.0))):.1f}"
                            rank_str = str(int(row_obj.get('Rank', row_obj.get('rank', 0))))
                            block_str = str(row_obj.get('category', row_obj.get('blockname', row_obj.get('hy', '--'))))
                            if block_str == 'nan' or block_str == 'None':
                                block_str = '--'
                        except Exception:
                            row_obj = None

                code_str = str(code).strip().zfill(6)
                if (name == "--" or not name.strip()) and row_obj is not None:
                    name = str(row_obj.get("name", row_obj.get("Name", "--"))).strip()
                if name == "--" or not name.strip():
                    try:
                        from sys_utils import resolve_stock_name
                        name = resolve_stock_name(code_str)
                    except Exception:
                        name = "--"

                if block_str == '--' or not block_str:
                    block_str = self._block_cache.get(code_str, '--')

                tag = "flat"
                if pct > 0:
                    tag = "up"
                elif pct < 0:
                    tag = "down"

                is_fav = code_str in fav_stocks
                display_name = f"★ {name}" if is_fav else name
                tags = [tag]
                if is_fav:
                    tags.append("favorite")

                if block_str and block_str not in ('--', 'nan', 'None'):
                    self._block_cache[code_str] = block_str

                # 历史公式过滤
                if has_query:
                    if code_str not in matched_codes:
                        continue

                # 概念过滤
                if getattr(self, 'selected_concept', None) is not None:
                    import re
                    cats = [c.strip() for c in re.split(r'[;；,，/|]', block_str) if c.strip()]
                    if self.selected_concept not in cats:
                        continue

                # 仅将实际展示/命中的个股放入统计字典
                if block_str and block_str not in ('--', 'nan', 'None'):
                    all_stocks_for_stats[code_str] = {
                        "name": name,
                        "percent": pct,
                        "category": block_str,
                        "close": price_str,
                        "ma5d": row_obj.get('ma5d', 0.0) if row_obj is not None else 0.0,
                        "ma20d": row_obj.get('ma20d', 0.0) if row_obj is not None else 0.0,
                        "ma60d": row_obj.get('ma60d', 0.0) if row_obj is not None else 0.0,
                        "rank": int(row_obj.get('Rank', row_obj.get('rank', 0))) if row_obj is not None else 0,
                    }

                # 尝试多级回退获取有效参考价格
                eff_price = 0.0
                if price_str != "--":
                    try:
                        eff_price = float(price_str)
                    except Exception:
                        eff_price = 0.0
                if eff_price <= 0.0 and quote:
                    eff_price = float(quote.get("last_close", quote.get("close", quote.get("price", 0.0))))
                if eff_price <= 0.0 and row_obj is not None:
                    eff_price = float(row_obj.get("last_close", row_obj.get("prev_close", 0.0)))
                
                if eff_price > 0.0 and price_str == "--":
                    price_str = f"{eff_price:.2f}"

                # 提取/推导 4 大实战决策列
                ladder_role = (
                    "🔥 强势首板" if pct >= 9.8 else ("🚀 冲锋冲板" if pct >= 5.0 else "⏱️ 潜伏震荡")
                )
                bid_p_str = "买压 80%"
                pioneer_str = "💎 逆势破局" if pct >= 3.0 else "⏱️ 同步博弈"
                
                if eff_price > 0.0:
                    decision_str = f"👑 挂单 {eff_price:.2f}元" if pct >= 7.0 else f"🔥 均线低吸 {eff_price:.2f}元"
                else:
                    decision_str = "👑 09:25竞价定盘挂单" if pct >= 7.0 else "🔥 开盘回踩均线低吸"

                # 基础列 + 自定义追加列
                extra_vals = _read_extra_vals(row_obj)
                row_values = (display_rank, code, display_name, f"{pct:.2f}",
                              price_str, ladder_role, bid_p_str, pioneer_str, decision_str,
                              dff2_str, dff3_str, rank_str) + extra_vals
                tree.insert("", "end", values=row_values, tags=tuple(tags))
                display_rank += 1

        # 3. 填充前4个表并过滤去重
        populate(self.tree_em, em_data)
        populate(self.tree_ths, ths_data)
        populate(self.tree_lh, lh_data)
        populate(self.tree_tgb, tgb_data)

        # 4. 填充共振"合"表，并自选置顶排序
        sorted_res = sorted(
            resonance_results,
            key=lambda x: 0 if str(x["code"]).strip().zfill(6) in fav_stocks else 1
        )
        for rank, item in enumerate(sorted_res, 1):
            code = item["code"]
            quote = quotes.get(code, {"name": "--", "percent": 0.0})
            name = quote["name"]
            pct = quote["percent"]

            price_str = "--"
            dff2_str = "--"
            dff3_str = "--"
            rank_str = "--"
            block_str = "--"
            row_obj_res = None

            if df_cache is not None and not df_cache.empty:
                code_str = str(code).strip().zfill(6)
                if code_str in df_cache.index:
                    try:
                        row_obj_res = df_cache.loc[code_str]
                        import pandas as pd
                        if isinstance(row_obj_res, pd.DataFrame):
                            row_obj_res = row_obj_res.iloc[0]
                        pct = float(row_obj_res.get('percent', row_obj_res.get('ratio', pct)))
                        price_str = f"{float(row_obj_res.get('trade', row_obj_res.get('close', row_obj_res.get('price', 0.0)))):.2f}"
                        dff2_str = f"{float(row_obj_res.get('dff2', row_obj_res.get('DFF2', 0.0))):.1f}"
                        dff3_str = f"{float(row_obj_res.get('dff3', row_obj_res.get('DFF3', 0.0))):.1f}"
                        rank_str = str(int(row_obj_res.get('Rank', row_obj_res.get('rank', 0))))
                        block_str = str(row_obj_res.get('category', row_obj_res.get('blockname', row_obj_res.get('hy', '--'))))
                        if block_str == 'nan' or block_str == 'None':
                            block_str = '--'
                    except Exception:
                        row_obj_res = None

            code_str = str(code).strip().zfill(6)
            if (name == "--" or not name.strip()) and row_obj_res is not None:
                name = str(row_obj_res.get("name", row_obj_res.get("Name", "--"))).strip()
            if name == "--" or not name.strip():
                try:
                    from sys_utils import resolve_stock_name
                    name = resolve_stock_name(code_str)
                except Exception:
                    name = "--"

            if block_str == '--' or not block_str:
                block_str = self._block_cache.get(code_str, '--')

            tag = "flat"
            if pct > 0:
                tag = "up"
            elif pct < 0:
                tag = "down"

            is_fav = code_str in fav_stocks
            display_name = f"★ {name}" if is_fav else name
            tags = [tag]
            if is_fav:
                tags.append("favorite")

            if block_str and block_str not in ('--', 'nan', 'None'):
                self._block_cache[code_str] = block_str

            # 历史公式过滤
            if has_query:
                if code_str not in matched_codes:
                    continue

            # 概念过滤
            if getattr(self, 'selected_concept', None) is not None:
                import re
                cats = [c.strip() for c in re.split(r'[;；,，/|]', block_str) if c.strip()]
                if self.selected_concept not in cats:
                    continue

            # 仅将实际展示/命中的个股放入统计字典
            if block_str and block_str not in ('--', 'nan', 'None'):
                all_stocks_for_stats[code_str] = {
                    "name": name,
                    "percent": pct,
                    "category": block_str,
                    "close": price_str,
                    "ma5d": row_obj_res.get('ma5d', 0.0) if row_obj_res is not None else 0.0,
                    "ma20d": row_obj_res.get('ma20d', 0.0) if row_obj_res is not None else 0.0,
                    "ma60d": row_obj_res.get('ma60d', 0.0) if row_obj_res is not None else 0.0,
                    "rank": int(row_obj_res.get('Rank', row_obj_res.get('rank', 0))) if row_obj_res is not None else 0,
                }

            # 尝试多级回退获取有效参考价格
            eff_price_res = 0.0
            if price_str != "--":
                try:
                    eff_price_res = float(price_str)
                except Exception:
                    eff_price_res = 0.0
            if eff_price_res <= 0.0 and quote:
                eff_price_res = float(quote.get("last_close", quote.get("close", quote.get("price", 0.0))))
            if eff_price_res <= 0.0 and row_obj_res is not None:
                eff_price_res = float(row_obj_res.get("last_close", row_obj_res.get("prev_close", 0.0)))
            if eff_price_res > 0.0 and price_str == "--":
                price_str = f"{eff_price_res:.2f}"

            # 提取共振分析已推演计算的 4 大决策字段
            ladder_role = item.get("ladder_role", "")
            if not ladder_role:
                ladder_role = "🔥 强势首板" if pct >= 9.8 else ("🚀 冲锋冲板" if pct >= 5.0 else "⏱️ 潜伏震荡")

            bid_p = float(item.get("bid_pressure", 80.0))
            seal_amt_wan = float(item.get("seal_amount_wan", 0.0))
            bid_p_str = f"{bid_p:.0f}%|{seal_amt_wan/10000.0:.1f}亿" if seal_amt_wan >= 10000 else (
                f"{bid_p:.0f}%|{seal_amt_wan:.0f}万" if seal_amt_wan > 0 else f"{bid_p:.0f}%"
            )

            pioneer_str = item.get("pioneer_tag", "")
            if not pioneer_str:
                pioneer_str = "💎 逆势冰点破局" if pct >= 3.0 else "⏱️ 同步博弈"

            entry_act = item.get("entry_action", "")
            sugg_p = float(item.get("suggested_price", 0.0))
            if sugg_p <= 0.0 and eff_price_res > 0.0:
                sugg_p = eff_price_res

            if entry_act and sugg_p > 0:
                decision_str = f"{entry_act} {sugg_p:.2f}元"
            elif entry_act:
                decision_str = entry_act
            elif eff_price_res > 0:
                decision_str = f"👑 挂单 {eff_price_res:.2f}元" if pct >= 7.0 else f"🔥 均线低吸 {eff_price_res:.2f}元"
            else:
                decision_str = "👑 09:25竞价定盘挂单" if pct >= 7.0 else "🔥 开盘回踩均线低吸"

            # 共振表同样追加 12 列基础列 + 自定义列
            extra_vals_res = _read_extra_vals(row_obj_res)
            row_values_res = (rank, code, display_name, f"{pct:.2f}",
                              price_str, ladder_role, bid_p_str, pioneer_str, decision_str,
                              dff2_str, dff3_str, rank_str) + extra_vals_res
            self.tree_res.insert("", "end", values=row_values_res, tags=tuple(tags))

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

        # 7. 更新顶部板块热点排名
        self.update_concept_ranking(all_stocks_for_stats)

        self.lbl_status.config(text="更新完成", fg="blue")

        # 8. 自动更新当前下拉框中历史公式的策略命中统计数
        try:
            self.calculate_history_hits_ui()
        except Exception as e:
            service_logger.debug(f"Auto calculate hits failed: {e}")


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
            self.save_config_settings()
            
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
            self.save_config_settings()

    def _show_calendar(self):
        if hasattr(self, 'date_entry'):
            try:
                self.date_entry.drop_down()
            except Exception:
                pass

    def _refresh_calendar_highlights(self):
        if not HAS_CALENDAR or not hasattr(self, 'date_entry'):
            return
        try:
            csv_dir = os.path.join(get_app_root(), "datacsv")
            if not os.path.exists(csv_dir):
                return
                
            dates = []
            for filename in os.listdir(csv_dir):
                if filename.startswith("popularity_resonance_"):
                    if filename.endswith(".csv.gz"):
                        date_str = filename[len("popularity_resonance_"):-7]
                    elif filename.endswith(".csv"):
                        date_str = filename[len("popularity_resonance_"):-4]
                    else:
                        continue
                    dates.append(date_str)
                    
            if not dates:
                return
                
            # ✅ [OPTIMIZE] 防抖：如果日期集合没变，跳过刷新
            dates_sig = hash(tuple(sorted(dates)))
            if getattr(self, '_last_calendar_sig', None) == dates_sig:
                return
            self._last_calendar_sig = dates_sig
            
            # 获取 DateEntry 内部的 Calendar 实例
            cal = self.date_entry._calendar
            
            # 清除之前的事件标签 (如果有)
            cal.calevent_remove('all', 'has_data')
            
            # 配置高亮样式: 红色背景 (代表该日有选股数据，跟策略选股一致)
            cal.tag_config('has_data', background='red', foreground='white')
            
            for date_str in dates:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    cal.calevent_create(dt, "有数据", "has_data")
                except Exception:
                    pass
            service_logger.info(f"✅ 人气共振日历已高亮 {len(dates)} 个日期")
        except Exception as e:
            service_logger.debug(f"刷新日历高亮失败: {e}")

    def on_date_changed(self, event=None):
        if hasattr(self, 'date_entry'):
            selected_date = self.date_entry.get_date().strftime("%Y-%m-%d")
        elif hasattr(self, 'date_var'):
            selected_date = self.date_var.get().strip()
        else:
            return
            
        if selected_date == self.current_date:
            return
            
        self.current_date = selected_date
        self.load_history_by_date(selected_date)

    def shift_date(self, delta):
        try:
            # 1. 扫描 datacsv 提取所有有数据的历史日期
            csv_dir = os.path.join(get_app_root(), "datacsv")
            valid_dates = set()
            if os.path.exists(csv_dir):
                import re
                pattern = re.compile(r"popularity_resonance_(\d{4}-\d{2}-\d{2})\.csv(?:\.gz)?")
                for filename in os.listdir(csv_dir):
                    m = pattern.match(filename)
                    if m:
                        valid_dates.add(m.group(1))

            # 2. 把今天也作为有效日期加入进去（因为今天可能有实时数据或今日已生成）
            today = time.strftime("%Y-%m-%d")
            valid_dates.add(today)

            # 3. 排序并查找最接近的日期
            sorted_dates = sorted(list(valid_dates))
            new_date_str = None

            if not sorted_dates:
                # 没有任何有效日期时，退避回原有的一天增减逻辑
                curr_d = datetime.strptime(self.current_date, "%Y-%m-%d")
                new_d = curr_d + timedelta(days=delta)
                new_date_str = new_d.strftime("%Y-%m-%d")
            else:
                curr_date_str = self.current_date
                if curr_date_str in sorted_dates:
                    idx = sorted_dates.index(curr_date_str)
                    if delta > 0:
                        if idx < len(sorted_dates) - 1:
                            new_date_str = sorted_dates[idx + 1]
                        else:
                            self.lbl_status.config(text="已切换至最晚的有数据日期", fg="blue")
                            return
                    else:
                        if idx > 0:
                            new_date_str = sorted_dates[idx - 1]
                        else:
                            self.lbl_status.config(text="已切换至最早的有数据日期", fg="blue")
                            return
                else:
                    # 如果当前日期不在列表中，进行区间逼近搜索
                    if delta > 0:
                        for d_str in sorted_dates:
                            if d_str > curr_date_str:
                                new_date_str = d_str
                                break
                    else:
                        for d_str in reversed(sorted_dates):
                            if d_str < curr_date_str:
                                new_date_str = d_str
                                break
                    
                    if not new_date_str:
                        # 没找到更晚/更早的，退避回增减一天
                        curr_d = datetime.strptime(curr_date_str, "%Y-%m-%d")
                        new_d = curr_d + timedelta(days=delta)
                        new_date_str = new_d.strftime("%Y-%m-%d")

            new_d = datetime.strptime(new_date_str, "%Y-%m-%d")
            self.current_date = new_date_str
            if hasattr(self, 'date_entry'):
                self.date_entry.set_date(new_d)
            elif hasattr(self, 'date_var'):
                self.date_var.set(new_date_str)
            self.load_history_by_date(new_date_str)
        except Exception as e:
            service_logger.error(f"微调日期失败: {e}")

    def load_history_by_date(self, date_str):
        csv_dir = os.path.join(get_app_root(), "datacsv")
        gz_path = os.path.join(csv_dir, f"popularity_resonance_{date_str}.csv.gz")
        csv_path = os.path.join(csv_dir, f"popularity_resonance_{date_str}.csv")

        file_path = None
        if os.path.exists(gz_path):
            file_path = gz_path
        elif os.path.exists(csv_path):
            file_path = csv_path

        if not file_path:
            today = time.strftime("%Y-%m-%d")
            if date_str == today:
                self.lbl_status.config(text="今天尚未持久化数据，等待数据同步...", fg="blue")
                return False
            self.clear_all_trees()
            self.lbl_status.config(text=f"无 {date_str} 的历史数据", fg="red")
            return False

        try:
            import pandas as pd
            df = pd.read_csv(file_path, encoding="utf-8")
            self._history_df = df

            # 💥 一定要在载入历史数据一开始清空原有表格，防止切换或重新载入日期时旧数据残留和重复！
            self.clear_all_trees()

            # 追加或保留板块缓存（历史数据也要支持双击查板块）
            if not hasattr(self, "_block_cache") or self._block_cache is None:
                self._block_cache = {}
            # 用于统计前 10 概念热度的个股信息收集字典
            all_stocks_for_stats = {}

            # 检测 CSV 中实际存在哪些自定义列，不再死板取实时 extra_cols，实现完全的自适应
            csv_cols = df.columns.tolist()
            ignored = {"code", "name", "score", "em_rank", "ths_rank", "lh_rank", "tgb_rank", "price", "percent", "dff2", "dff3", "rank", "block"}
            available_extra = [c for c in csv_cols if c not in ignored]

            # 缓存当前使用的额外列，供双击 constituent 个股二级弹窗等自适应对齐使用
            self.current_extra_cols = available_extra

            # 动态重新配置 5 个 Treeview 的列
            self._reconfigure_tree_columns(self.tree_em, "东", available_extra)
            self._reconfigure_tree_columns(self.tree_ths, "花", available_extra)
            self._reconfigure_tree_columns(self.tree_lh, "龙", available_extra)
            self._reconfigure_tree_columns(self.tree_tgb, "淘", available_extra)
            self._reconfigure_tree_columns(self.tree_res, "合", available_extra)

            em_list = []
            ths_list = []
            lh_list = []
            tgb_list = []
            res_list = []

            def safe_str(val, default="--"):
                if pd.isna(val) or str(val).strip().lower() in ('nan', 'none', ''):
                    return default
                return str(val).strip()

            for _, row in df.iterrows():
                code = str(row.get("code", "")).strip().split('.')[0].zfill(6)
                name = safe_str(row.get("name"), default="--")
                # 💥 补齐个股名称兜底解析：防止单独运行、无缓存时历史个股名称全显示为 '--' 的情况
                if name == "--" or not name.strip():
                    try:
                        from sys_utils import resolve_stock_name
                        name = resolve_stock_name(code)
                    except Exception:
                        name = "--"

                score_val = row.get("score", 0)
                score = 0
                if pd.notna(score_val):
                    try:
                        score = int(float(score_val))
                    except ValueError:
                        score = 0

                price   = safe_str(row.get("price"))
                percent = safe_str(row.get("percent"))
                dff2    = safe_str(row.get("dff2"))
                dff3    = safe_str(row.get("dff3"))
                rank    = safe_str(row.get("rank"))
                block   = safe_str(row.get("block"))

                # 写入板块缓存，供双击查询
                if block and block != '--':
                    self._block_cache[code] = block
                    try:
                        pct_val = float(str(percent).replace('%', ''))
                    except (ValueError, TypeError):
                        pct_val = 0.0
                    all_stocks_for_stats[code] = {
                        "name": name,
                        "percent": pct_val,
                        "category": block,
                        "close": price,
                        "ma5d": 0.0,
                        "ma20d": 0.0,
                        "ma60d": 0.0,
                        "rank": rank
                    }

                # 读取自适应历史列值（CSV 中有则取，否则 '--'）
                extra_vals = tuple(safe_str(row.get(c)) for c in available_extra)

                # 基础列构成固定 8 元 + 自定义列（不含 block）
                base_row = (percent, price, dff2, dff3, rank)
                # 完整行元组：(rank_or_score, code, name, percent, price, dff2, dff3, rank) + extra_vals
                full_item_base = (code, name, percent, price, dff2, dff3, rank) + extra_vals

                em_rank = row.get("em_rank")
                if pd.notna(em_rank) and str(em_rank).strip() and str(em_rank).strip().lower() not in ('nan', 'none'):
                    try:
                        em_list.append((int(float(em_rank)),) + full_item_base)
                    except ValueError:
                        pass

                ths_rank = row.get("ths_rank")
                if pd.notna(ths_rank) and str(ths_rank).strip() and str(ths_rank).strip().lower() not in ('nan', 'none'):
                    try:
                        ths_list.append((int(float(ths_rank)),) + full_item_base)
                    except ValueError:
                        pass

                lh_rank = row.get("lh_rank")
                if pd.notna(lh_rank) and str(lh_rank).strip() and str(lh_rank).strip().lower() not in ('nan', 'none'):
                    try:
                        lh_list.append((int(float(lh_rank)),) + full_item_base)
                    except ValueError:
                        pass

                tgb_rank = row.get("tgb_rank")
                if pd.notna(tgb_rank) and str(tgb_rank).strip() and str(tgb_rank).strip().lower() not in ('nan', 'none'):
                    try:
                        tgb_list.append((int(float(tgb_rank)),) + full_item_base)
                    except ValueError:
                        pass

                res_list.append((score,) + full_item_base)

            # 获取全局自选股代码集合
            try:
                from global_favorites import GlobalFavoriteManager
                fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
            except Exception:
                fav_stocks = set()

            def list_sort_key(item, reverse_sub=False):
                code = item[1]
                code_str = str(code).strip().zfill(6)
                is_fav = 0 if code_str in fav_stocks else 1
                sub_val = item[0]
                if reverse_sub:
                    return (is_fav, -sub_val)
                return (is_fav, sub_val)

            em_list.sort(key=lambda x: list_sort_key(x, reverse_sub=False))
            ths_list.sort(key=lambda x: list_sort_key(x, reverse_sub=False))
            lh_list.sort(key=lambda x: list_sort_key(x, reverse_sub=False))
            tgb_list.sort(key=lambda x: list_sort_key(x, reverse_sub=False))
            res_list.sort(key=lambda x: list_sort_key(x, reverse_sub=True))

            # 列数 = 8个基础列 + len(_extra_cols)（block 已移除）
            def fill_tree(tree, data_list):
                for idx, item in enumerate(data_list):
                    # item: (rank_or_score, code, name, percent, price, dff2, dff3, rank_val, *extra_vals)
                    rank_or_score = item[0]
                    code = item[1]
                    name = item[2]
                    rest = item[3:]  # percent, price, dff2, dff3, rank_val, *extra_vals
                    display_idx = idx + 1

                    code_str = str(code).strip().zfill(6)
                    is_fav = code_str in fav_stocks
                    display_name = f"★ {name}" if is_fav else name

                    tag = "flat"
                    try:
                        p_val = float(str(item[3]).replace('%', ''))
                        if p_val > 0: tag = "up"
                        elif p_val < 0: tag = "down"
                    except (ValueError, TypeError):
                        pass

                    tags = [tag]
                    if is_fav:
                        tags.append("favorite")

                    # values = (显示序号, code, name, percent, price, dff2, dff3, rank, *extra_vals)
                    values = (display_idx, code, display_name) + rest
                    tree.insert("", "end", values=values, tags=tuple(tags))

            fill_tree(self.tree_em, em_list)
            fill_tree(self.tree_ths, ths_list)
            fill_tree(self.tree_lh, lh_list)
            fill_tree(self.tree_tgb, tgb_list)
            fill_tree(self.tree_res, res_list)

            self.resonance_codes = [x[1] for x in res_list]
            self.refresh_layout(len(em_list)==0, len(ths_list)==0, len(lh_list)==0, len(res_list)==0, len(tgb_list)==0)

            # 对所有具有排序状态的表格进行排序自愈
            for tree in (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res):
                if getattr(tree, "sort_col", None) is not None:
                    self.sort_column(tree, tree.sort_col, getattr(tree, "sort_descending", False), auto_restore=True)

            # 更新顶部板块热点排名
            self.update_concept_ranking(all_stocks_for_stats)

            self.lbl_status.config(text=f"已加载 {date_str} 历史数据", fg="darkgreen")
            return True
        except Exception as e:
            service_logger.error(f"加载 {date_str} 历史数据失败: {e}")
            self.lbl_status.config(text=f"加载失败: {e}", fg="red")
            return False

    def open_history_data(self):
        from tkinter import filedialog
        csv_dir = os.path.join(get_app_root(), "datacsv")
        os.makedirs(csv_dir, exist_ok=True)
        
        file_path = filedialog.askopenfilename(
            initialdir=csv_dir,
            title="选择历史共振数据",
            filetypes=[
                ("CSV/GZ Files", "*.csv *.csv.gz"),
                ("Compressed GZ", "*.csv.gz"),
                ("Normal CSV", "*.csv"),
                ("All Files", "*.*")
            ]
        )
        if not file_path:
            return
            
        filename = os.path.basename(file_path)
        date_str = None
        if filename.startswith("popularity_resonance_"):
            if filename.endswith(".csv.gz"):
                date_str = filename[len("popularity_resonance_"):-7]
            elif filename.endswith(".csv"):
                date_str = filename[len("popularity_resonance_"):-4]
                
        if date_str:
            if hasattr(self, 'date_entry'):
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    self.date_entry.set_date(dt)
                except Exception:
                    pass
            elif hasattr(self, 'date_var'):
                self.date_var.set(date_str)
            self.current_date = date_str
            self.load_history_by_date(date_str)
        else:
            messagebox.showerror("错误", "非标准的人气共振数据 CSV/GZ 文件")

    def save_daily_resonance_csv(self, em_data, ths_data, lh_data, tgb_data, resonance_results, all_quotes, force_save=False):
        # 1. 交易日及盘后判定限制
        try:
            if not force_save and not cct.get_trade_date_status():
                service_logger.info("今日非交易日，无需持久化盘后数据。")
                return
        except Exception as otc_err:
            service_logger.debug(f"交易日判定服务异常: {otc_err}")
            
        try:
            import pandas as pd
            csv_dir = os.path.join(get_app_root(), "datacsv")
            os.makedirs(csv_dir, exist_ok=True)
            
            today = time.strftime("%Y-%m-%d")
            # 自动保存为压缩过的 .csv.gz 格式
            csv_path = os.path.join(csv_dir, f"popularity_resonance_{today}.csv.gz")
            
            current_df = self.sync_manager.get_current_df()
            
            rows = []
            for r in resonance_results:
                code = r.get('code', '')
                score = r.get('score', 0)
                
                # 优先从 all_quotes 或 current_df 提取正确的股票名称，防止出现空值 and nan
                name = ""
                if code in all_quotes:
                    name = all_quotes[code].get('name', '')
                
                if not name and current_df is not None and code in current_df.index:
                    s_row = current_df.loc[code]
                    import pandas as pd
                    if isinstance(s_row, pd.DataFrame):
                        s_row = s_row.iloc[0]
                    name = s_row.get("name", s_row.get("Name", ''))
                    
                if not name:
                    name = r.get('name', '')
                    
                if not name or str(name).strip().lower() in ('nan', 'none', ''):
                    name = '--'
                
                row = {
                    "code": code,
                    "name": name,
                    "score": score,
                    "em_rank": em_data.get(code, ''),
                    "ths_rank": ths_data.get(code, ''),
                    "lh_rank": lh_data.get(code, ''),
                    "tgb_rank": tgb_data.get(code, ''),
                }
                
                price_val = "--"
                percent_val = "--"
                dff2_val = "--"
                dff3_val = "--"
                rank_val = "--"
                block_val = "--"
                
                if current_df is not None and code in current_df.index:
                    s_row = current_df.loc[code]
                    import pandas as pd
                    if isinstance(s_row, pd.DataFrame):
                        s_row = s_row.iloc[0]
                    price_val = s_row.get("trade", s_row.get("price", "--"))
                    percent_val = s_row.get("percent", "--")
                    dff2_val = s_row.get("dff2", "--")
                    dff3_val = s_row.get("dff3", "--")
                    rank_val = s_row.get("Rank", s_row.get("rank", "--"))
                    block_val = s_row.get("category", "--")
                
                if price_val == "--" and code in all_quotes:
                    q = all_quotes[code]
                    price_val = q.get("price", "--")
                    percent_val = q.get("percent", "--")
                    
                def clean_field(val):
                    if pd.isna(val) or str(val).strip().lower() in ('nan', 'none', ''):
                        return "--"
                    return str(val).strip()

                row.update({
                    "price":   clean_field(price_val),
                    "percent": clean_field(percent_val),
                    "dff2":    clean_field(dff2_val),
                    "dff3":    clean_field(dff3_val),
                    "rank":    clean_field(rank_val),
                    "block":   clean_field(block_val)
                })

                # 追加自定义列到 CSV（支持将来新增列的持久化）
                _, _, _extra_cols = self._get_all_cols()
                for ec in _extra_cols:
                    ec_val = "--"
                    if current_df is not None and code in current_df.index:
                        try:
                            s_row2 = current_df.loc[code]
                            if isinstance(s_row2, pd.DataFrame):
                                s_row2 = s_row2.iloc[0]
                            v = None
                            for key in (ec, ec.lower(), ec.upper()):
                                try:
                                    v = s_row2.get(key)
                                except Exception:
                                    pass
                                if v is not None:
                                    break
                            if v is not None and str(v) not in ('nan', 'None', ''):
                                ec_val = clean_field(v)
                        except Exception:
                            pass
                    row[ec] = ec_val
                rows.append(row)
                
            if rows:
                df = pd.DataFrame(rows)
                # 使用 gzip 压缩格式进行持久化
                df.to_csv(csv_path, index=False, encoding="utf-8", compression="gzip")
                service_logger.info(f"每日人气共振数据已安全持久化（GZ压缩）: {csv_path}")
                # 如果是盘后，则标记今日盘后最终数据已成功持久化
                if time.strftime("%H:%M") >= "15:15":
                    self._final_post_market_saved_date = today
                # 写入成功后刷新一下日历高亮
                self.root.after(0, self._refresh_calendar_highlights)
        except Exception as e:
            service_logger.error(f"每日数据持久化 CSV.GZ 失败: {e}")

    def _check_auto_refresh_after_close(self):
        if not hasattr(self, 'root') or not self.root:
            return
        try:
            today = time.strftime("%Y-%m-%d")
            
            # 1. 检查今日是否已持久化
            csv_dir = os.path.join(get_app_root(), "datacsv")
            gz_path = os.path.join(csv_dir, f"popularity_resonance_{today}.csv.gz")
            csv_path = os.path.join(csv_dir, f"popularity_resonance_{today}.csv")
            has_persisted = os.path.exists(gz_path) or os.path.exists(csv_path)
            
            # 2. 检查是否是交易日
            is_trade_day = False
            try:
                is_trade_day = cct.get_trade_date_status()
            except Exception as e:
                service_logger.debug(f"检查交易日状态异常: {e}")
                
            if is_trade_day:
                # 3. 检查时间是否在 15:15 之后
                now_time_str = time.strftime("%H:%M")
                if now_time_str >= "15:15":
                    last_saved_date = getattr(self, '_final_post_market_saved_date', None)
                    # 如果今日尚未成功执行盘后最终保存（即使白天生成过部分数据文件），则强行触发最终的盘后刷新持久化
                    if last_saved_date != today:
                        import time as t_mod
                        now_ts = t_mod.time()
                        last_attempt = getattr(self, '_last_auto_save_attempt_time', 0.0)
                        fail_count = getattr(self, '_auto_save_fail_count', 0)
                        
                        # 冷却时间：至少间隔 5 分钟（300秒）才重试一次，防止异常时高频请求
                        if now_ts - last_attempt >= 300.0:
                            if not getattr(self, '_is_auto_saving_after_close', False):
                                self._is_auto_saving_after_close = True
                                self._last_auto_save_attempt_time = now_ts
                                service_logger.info(f"检测到收盘（15:15后）且今日最终盘后数据尚未持久化，启动自动刷新与持久化 (尝试次数: {fail_count + 1})...")
                                
                                def auto_job():
                                    try:
                                        self.root.after(0, lambda: self.lbl_status.config(text="自动同步数据中...", fg="blue"))
                                        # 自动查询并强制持久化数据
                                        self._run_once_job(force_save=True)
                                        # 延迟检测文件是否成功写入
                                        t_mod.sleep(5.0)
                                        if os.path.exists(gz_path) or os.path.exists(csv_path):
                                            self._auto_save_fail_count = 0
                                            self._final_post_market_saved_date = today  # 标记今天已完成最终持久化
                                            service_logger.info("收盘后自动同步并持久化人气共振数据成功。")
                                            self.root.after(0, lambda: self.lbl_status.config(text="收盘自动持久化完成", fg="darkgreen"))
                                        else:
                                            self._auto_save_fail_count = fail_count + 1
                                            service_logger.warning(f"收盘后自动同步数据未产生有效文件，当前失败次数: {self._auto_save_fail_count}")
                                            self.root.after(0, lambda: self.lbl_status.config(text="收盘自动持久化失败", fg="red"))
                                    except Exception as ex:
                                        self._auto_save_fail_count = fail_count + 1
                                        service_logger.error(f"收盘自动刷新持久化任务执行失败: {ex}")
                                        self.root.after(0, lambda: self.lbl_status.config(text=f"持久化异常: {ex}", fg="red"))
                                    finally:
                                        self._is_auto_saving_after_close = False
                                        
                                threading.Thread(target=auto_job, daemon=True).start()
        except Exception as e:
            service_logger.error(f"收盘自动刷新检测异常: {e}")
        finally:
            try:
                # 每 5 分钟 (300000 ms) 轮询检测一次状态，提升响应及时性
                self.root.after(300000, self._check_auto_refresh_after_close)
            except Exception:
                pass

    def update_concept_ranking(self, all_stocks):
        if not hasattr(self, 'dynamic_concepts_frame') or not self.dynamic_concepts_frame:
            return

        # 1. 物理清空 dynamic_concepts_frame 里的全部旧有组件
        for widget in self.dynamic_concepts_frame.winfo_children():
            widget.destroy()

        if not all_stocks:
            lbl_empty = tk.Label(self.dynamic_concepts_frame, text="暂无板块数据", font=("Microsoft YaHei", 9, "bold"), fg="gray")
            lbl_empty.pack(side="left")
            return

        import re
        concept_dict = {}
        concept_is_bullish = {}
        # 用来保存每个板块下的个股 data [(code, name, percent, volume, rank)]
        temp_cat_stocks = {}

        for code, info in all_stocks.items():
            cat_str = info.get("category", "")
            if not cat_str or cat_str in ("--", "nan", "None"):
                continue
            cats = [c.strip() for c in re.split(r'[;；,，/|]', cat_str) if c.strip()]
            pct = info.get("percent", 0.0)
            
            # 获取个股的基本属性并多层兜底
            name = info.get("name", "--")
            if not name or name == "--" or not str(name).strip():
                if hasattr(self, '_last_data_cache') and self._last_data_cache:
                    q_data = self._last_data_cache.get("quotes", {})
                    if code in q_data:
                        name = q_data[code].get("name", name)
            if not name or name == "--" or not str(name).strip():
                try:
                    from sys_utils import resolve_stock_name
                    name = resolve_stock_name(code)
                except Exception:
                    name = "--"
            
            try:
                close = float(info.get("close", 0.0))
                ma5 = float(info.get("ma5d", 0.0))
                ma20 = float(info.get("ma20d", 0.0))
                ma6 = float(info.get("ma60d", 0.0))
                is_bullish = (ma5 > ma20 > ma6) and (close > ma6)
            except Exception:
                is_bullish = False

            # 获取 Rank 属性
            rank_val = info.get("rank", info.get("Rank", 0))
            
            # 获取成交量 volume
            volume_val = info.get("volume", info.get("vol", info.get("amount", 0.0)))

            for cat in cats:
                if cat in ('', '0', 'nan', 'None'):
                    continue
                if cat not in concept_dict:
                    concept_dict[cat] = []
                    concept_is_bullish[cat] = []
                    temp_cat_stocks[cat] = []
                concept_dict[cat].append(pct)
                concept_is_bullish[cat].append(is_bullish)
                temp_cat_stocks[cat].append((code, name, pct, volume_val, rank_val))

        concept_score = []
        for cat, percents in concept_dict.items():
            if not percents:
                continue
            cnt = len(percents)
            total_pct = sum(percents)
            avg_pct = total_pct / cnt
            bullish_list = concept_is_bullish.get(cat, [])
            bullish_ratio = sum(bullish_list) / len(bullish_list) if bullish_list else 0.0
            
            # 🚀【板块热度加权】：板块异动个股越多权重越大！
            # 综合板块总动量(总涨幅 sum(pct))与只数群聚分(Count * 10.0)，辅以多头趋势加成：
            # Score = (TotalPct + Count * 10.0) * (1.0 + 0.5 * BullishRatio) * 10.0
            if total_pct > 0:
                base_energy = total_pct + (cnt * 10.0)
                score = base_energy * (1.0 + 0.5 * bullish_ratio) * 10.0
            else:
                score = (total_pct - cnt * 5.0) * (1.0 + 0.5 * bullish_ratio) * 10.0
            
            concept_score.append({
                "name": cat,
                "score": round(score, 2),
                "avg_percent": round(avg_pct, 2),
                "count": cnt,
                "bullish_ratio": round(bullish_ratio, 2)
            })

        # ── 过滤与排序逻辑 ──
        # 1. 优先选取成员数 >= 2 的有效概念 (过滤杂音)
        valid_scores = [x for x in concept_score if x["count"] >= 2]
        valid_scores.sort(key=lambda x: (
            1 if self._is_noise_concept(x["name"]) else 0,
            -x["score"],
            -x["count"],
            -x["avg_percent"]
        ))
        
        # 2. 如果 valid_scores 数量不足 5 个，平滑降级从 count < 2 中补充非噪声概念
        if len(valid_scores) < 5:
            remaining = [x for x in concept_score if x["count"] < 2]
            remaining.sort(key=lambda x: (
                1 if self._is_noise_concept(x["name"]) else 0,
                -x["score"],
                -x["count"],
                -x["avg_percent"]
            ))
            top_candidates = valid_scores + remaining
        else:
            top_candidates = valid_scores

        top5 = top_candidates[:5]

        if not top5:
            lbl_empty = tk.Label(self.dynamic_concepts_frame, text="暂无板块数据", font=("Microsoft YaHei", 9, "bold"), fg="gray")
            lbl_empty.pack(side="left")
        else:
            # 动态生成各概念板块，点击直接弹出二级 Constituents 弹窗，并提供视觉悬浮微动画
            for item in top5:
                c_name = item['name']
                c_count = item['count']
                c_avg_pct = item['avg_percent']
                
                lbl_c = tk.Label(
                    self.dynamic_concepts_frame,
                    text=f"{c_name}:{c_count}只({c_avg_pct:+.1f}%)",
                    font=("Microsoft YaHei", 9, "bold", "underline"),
                    fg="green",
                    cursor="hand2"
                )
                lbl_c.pack(side="left", padx=6)
                
                # 绑定点击事件：直接打开对应板块的个股 constituents 列表窗口！
                lbl_c.bind("<Button-1>", lambda e, name=c_name: self.show_concept_top10_window(name))
                
                # 绑定鼠标悬浮变色（深绿/绿），增加 premium 的交互感
                lbl_c.bind("<Enter>", lambda e, w=lbl_c: w.config(fg="#004D00"))
                lbl_c.bind("<Leave>", lambda e, w=lbl_c: w.config(fg="green"))

        # 缓存全量概念及其所占人气股只数（强度），用于右键点击查看最强概念板块个股列表
        self._all_concept_scores = {item["name"]: item["count"] for item in concept_score}

        # 模仿 tk 保存当前的板块字典，个股按涨幅从大到小排序
        self._last_categories = [item["name"] for item in top5]
        self._last_cat_dict = {}
        for cat in self._last_categories:
            # 排序个股
            stocks = temp_cat_stocks.get(cat, [])
            stocks.sort(key=lambda x: x[2], reverse=True)
            self._last_cat_dict[cat] = stocks

    def show_concept_detail_window(self):
        """弹出详细概念异动窗口（复用+自动刷新+键盘/滚轮+高亮）"""
        if not hasattr(self, "_last_categories") or not self._last_categories:
            messagebox.showinfo("提示", "暂无概念板块数据，请先执行查询或等待实时行情推送。")
            return

        # 检查窗口是否已存在
        if getattr(self, "_concept_win", None):
            try:
                if self._concept_win.winfo_exists():
                    win = self._concept_win
                    win.deiconify()
                    win.lift()
                    # 仅清理旧内容区，不销毁窗口结构
                    for widget in win._content_frame.winfo_children():
                        widget.destroy()
                    self.update_concept_detail_content()
                    return
                else:
                    self._concept_win = None
            except Exception:
                self._concept_win = None

        win = tk.Toplevel(self.root)
        self._concept_win = win
        win.title("概念板块统计详情")
        
        # 恢复窗口几何尺寸，默认 240x450
        saved_geo = self.config.get("concept_detail_window_geometry", "240x450")
        try:
            win.geometry(saved_geo)
        except Exception:
            win.geometry("240x450")

        # 监听大小与坐标变化以保存布局
        def _save_concept_detail_win_geo(event):
            if win.winfo_exists():
                try:
                    self.config["concept_detail_window_geometry"] = win.winfo_geometry()
                except Exception:
                    pass
        win.bind("<Configure>", _save_concept_detail_win_geo)

        # 主Frame + Canvas + 滚动
        frame = tk.Frame(win, bg="white")
        frame.pack(fill="both", expand=True, padx=4, pady=4)

        canvas = tk.Canvas(frame, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview, style="Slim.Vertical.TScrollbar")
        scroll_frame = tk.Frame(canvas, bg="white")

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 鼠标滚轮绑定
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        def unbind_mousewheel(event=None):
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except Exception:
                pass

        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)

        # 保存引用
        win._canvas = canvas
        win._content_frame = scroll_frame
        win._unbind_mousewheel = unbind_mousewheel

        # 键盘滚动与高亮初始化
        self._label_widgets = []
        self._selected_index = 0

        win.bind("<Up>", self._on_detail_key)
        win.bind("<Down>", self._on_detail_key)
        win.bind("<Escape>", lambda e: on_close_detail_window())
        
        # 获取焦点
        win.focus_set()

        # 关闭窗口
        def on_close_detail_window():
            if win.winfo_exists():
                try:
                    self.config["concept_detail_window_geometry"] = win.winfo_geometry()
                except Exception:
                    pass
            unbind_mousewheel()
            win.destroy()
            self._concept_win = None

        win.protocol("WM_DELETE_WINDOW", on_close_detail_window)

        # 初始内容
        self.update_concept_detail_content()

    def update_concept_detail_content(self, limit=10):
        """刷新概念详情窗口内容"""
        if not hasattr(self, "_concept_win") or not self._concept_win:
            return
        if not self._concept_win.winfo_exists():
            self._concept_win = None
            return

        scroll_frame = self._concept_win._content_frame
        canvas = self._concept_win._canvas

        # 清空旧内容
        for widget in scroll_frame.winfo_children():
            widget.destroy()
        self._label_widgets = []

        current_categories = getattr(self, "_last_categories", [])
        cat_dict = getattr(self, "_last_cat_dict", {})

        # 在顶部加一个小标题
        title_lbl = tk.Label(
            scroll_frame,
            text="📊 概念异动板块详情 (前5)",
            font=("Microsoft YaHei", 9, "bold"),
            fg="#004D40",
            bg="white",
            anchor="w"
        )
        title_lbl.pack(anchor="w", pady=(2, 6), padx=4)

        # 获取主窗口当前的排序状态，支持与主窗口同步
        main_sort_col = getattr(self.tree_res, "sort_col", self.config.get("sort_col", "val"))
        if main_sort_col == "percent":
            main_sort_col = "val"
        main_sort_descending = getattr(self.tree_res, "sort_descending", self.config.get("sort_descending", True))
        
        # 将主排序列名映射为 5 元组的索引
        col_to_idx = {
            "val": 2,
            "percent": 2,
            "volume": 3,
            "rank": 4,
            "code": 0,
            "name": 1
        }
        sort_idx = col_to_idx.get(main_sort_col, None)

        for c in current_categories[:5]:
            # 每个概念的标题行，点击也可以弹出具体板块个股窗口
            c_frame = tk.Frame(scroll_frame, bg="white")
            c_frame.pack(anchor="w", fill="x", pady=(6, 2))
            
            c_lbl = tk.Label(
                c_frame,
                text=f"📂 {c} ({len(cat_dict.get(c, []))}只)",
                fg="#1A237E",
                bg="white",
                font=("Microsoft YaHei", 9, "bold"),
                cursor="hand2",
                anchor="w"
            )
            c_lbl.pack(side="left", padx=4)
            c_lbl.bind("<Button-1>", lambda e, name=c: self.show_concept_top10_window(name))
            
            # 展示这个板块下的个股并排序
            stocks = list(cat_dict.get(c, []))
            if sort_idx is not None:
                def try_float(v):
                    try:
                        return float(str(v).replace('%', ''))
                    except Exception:
                        return 0.0
                if sort_idx in (2, 3, 4):
                    stocks.sort(key=lambda x: try_float(x[sort_idx]), reverse=main_sort_descending)
                else:
                    stocks.sort(key=lambda x: str(x[sort_idx]).lower(), reverse=main_sort_descending)
            
            stocks_to_show = stocks[:limit]
            for code, name, percent, volume, rank in stocks_to_show:
                # 仿照 tk 显示样式
                disp_text = f"  {code} {name:<4} R:{rank:<3} {percent:>+6.2f}%"
                
                fg_color = "#E02020" if percent > 0 else ("#20A020" if percent < 0 else "black")
                
                lbl = tk.Label(
                    scroll_frame,
                    text=disp_text,
                    fg=fg_color,
                    bg="white",
                    font=("Consolas", 9),
                    cursor="hand2",
                    anchor="w",
                    takefocus=True
                )
                lbl.pack(anchor="w", padx=10, pady=1)
                lbl._code = code
                lbl._concept = c
                
                idx = len(self._label_widgets)
                lbl.bind("<Button-1>", lambda e, cd=code, i=idx: self._on_label_click(cd, i))
                lbl.bind("<Double-Button-1>", lambda e, cd=code, name=c: self._on_label_double_click(cd, name))
                self._label_widgets.append(lbl)

        # 默认选中第一条
        if self._label_widgets:
            self._selected_index = 0
            self._label_widgets[0].configure(bg="#E0F7FA")

        canvas.yview_moveto(0)

    def _update_detail_selection(self, idx):
        """更新选中高亮并滚动"""
        if not hasattr(self, "_concept_win") or not self._concept_win:
            return
        canvas = self._concept_win._canvas
        scroll_frame = self._concept_win._content_frame

        for lbl in self._label_widgets:
            lbl.configure(bg="white")
        if 0 <= idx < len(self._label_widgets):
            lbl = self._label_widgets[idx]
            lbl.configure(bg="#E0F7FA")
            self._selected_index = idx

            canvas.update_idletasks()
            scroll_frame.update_idletasks()
            lbl_top = lbl.winfo_y()
            lbl_bottom = lbl_top + lbl.winfo_height()
            view_top = canvas.canvasy(0)
            view_bottom = view_top + canvas.winfo_height()
            if lbl_top < view_top:
                canvas.yview_moveto(lbl_top / max(1, scroll_frame.winfo_height()))
            elif lbl_bottom > view_bottom:
                canvas.yview_moveto((lbl_bottom - canvas.winfo_height()) / max(1, scroll_frame.winfo_height()))

    def _on_label_click(self, code, idx):
        """点击详情中个股标签，实现多视图滚动定位与通道联动"""
        self._update_detail_selection(idx)
        self.tree_scroll_to_code(code, vis=True)

    def _on_label_double_click(self, code, concept_name):
        """双击详情个股，直接弹出具体板块列表窗口"""
        self.show_concept_top10_window(concept_name)

    def _on_detail_key(self, event):
        """键盘上下键导航"""
        if not self._label_widgets:
            return
        idx = self._selected_index
        if event.keysym == "Up":
            idx = max(0, idx - 1)
        elif event.keysym == "Down":
            idx = min(len(self._label_widgets) - 1, idx + 1)
        self._update_detail_selection(idx)
        # 同步联动
        lbl = self._label_widgets[idx]
        self._on_label_click(lbl._code, idx)

    def show_concept_top10_window(self, concept_name):
        """
        [NEW] 复刻 tk 中的概念板块个股 Top10/Top50 幕口展示功能。
        已优化：支持历史复盘模式数据自动对齐、自适应自定义追加列、窗口复用自愈、Escape键关闭以及窗口位置记忆。
        以及：支持精准的中英文括号标准化匹配、跟人气主表一致的自选股优先多级排序及同步排序、以及底部上涨下跌股数与均幅统计。
        板块个股详情列（code, name, val, price, dff2, dff3, rank 等）已与人气排行主窗口完全对齐。
        """
        import re
        import pandas as pd

        target_concept = self._normalize_concept_name(concept_name)
        if not target_concept:
            return

        # 2. 确定是否是历史浏览模式
        today = time.strftime("%Y-%m-%d")
        current_view_date = self.date_entry.get().strip() if hasattr(self, "date_entry") else today
        is_history_mode = (current_view_date != today)

        df_all = self.sync_manager.get_current_df()
        # 自动对齐列：如果处于历史模式且已加载历史数据，则直接对齐当前历史列结构，否则使用实时配置列
        if is_history_mode and hasattr(self, "_history_df") and self._history_df is not None:
            csv_cols = self._history_df.columns.tolist()
            ignored = {"code", "name", "score", "em_rank", "ths_rank", "lh_rank", "tgb_rank", "price", "percent", "dff2", "dff3", "rank", "block"}
            extra_cols = [c for c in csv_cols if c not in ignored]
        else:
            _, _, extra_cols = self._get_all_cols()
        
        # 收集当前人气排行中真正存在的、包含此概念的个股
        matched_stocks = []

        def safe_str(val, default="--"):
            if pd.isna(val) or str(val).strip().lower() in ('nan', 'none', ''):
                return default
            return str(val).strip()

        # 1. 提取当前模式下正在显示的所有人气强势个股的数据行，并进行物理去重
        current_stocks = []
        seen_codes = set()
        if is_history_mode:
            if hasattr(self, "_history_df") and self._history_df is not None:
                for _, row in self._history_df.iterrows():
                    c = str(row.get("code", "")).strip().split('.')[0].zfill(6)
                    if c and c != "000000" and c not in seen_codes:
                        seen_codes.add(c)
                        current_stocks.append((c, row))
        else:
            # 严格从当前人气综合界面的 5 个表格中实际展示/载入的所有强势个股中提取！
            all_trees = (self.tree_em, self.tree_ths, self.tree_lh, self.tree_tgb, self.tree_res)
            for tree_w in all_trees:
                if not tree_w or not tree_w.winfo_exists():
                    continue
                cols = list(tree_w["columns"])
                code_idx = cols.index("code") if "code" in cols else 1
                for iid in tree_w.get_children():
                    vals = tree_w.item(iid, "values")
                    if vals and len(vals) > code_idx:
                        c = str(vals[code_idx]).strip().zfill(6)
                        if c and c != "000000" and c not in seen_codes:
                            seen_codes.add(c)
                            row_obj = None
                            if df_all is not None and c in df_all.index:
                                try:
                                    row_obj = df_all.loc[c]
                                    if isinstance(row_obj, pd.DataFrame):
                                        row_obj = row_obj.iloc[0]
                                except Exception:
                                    row_obj = None
                            current_stocks.append((c, row_obj))

        # 2. 遍历并匹配属于 target_concept 的股票
        for code_str, row in current_stocks:
            # 优先从 _block_cache 获取这只个股 of 板块，如果是历史模式且行内自带 block 则从中获取
            block_str = getattr(self, '_block_cache', {}).get(code_str, "")
            if not block_str or block_str in ("--", "nan", "None"):
                if hasattr(row, "get"):
                    block_str = safe_str(row.get("block"))
            
            if not block_str or block_str in ("--", "nan", "None"):
                continue

            cats = [c.strip() for c in re.split(r'[;；,，/|]', block_str) if c.strip()]
            cats_normalized = [self._normalize_concept_name(c) for c in cats]
            
            if target_concept in cats_normalized:
                name = "--"
                pct = 0.0
                price = 0.0
                rank_val = 0
                dff2 = 0.0
                dff3 = 0.0

                # 提取属性
                if is_history_mode:
                    try:
                        name = safe_str(row.get("name"))
                        # 补齐个股名称兜底解析：防止单独运行、无缓存时历史个股名称全显示为 '--' 的情况
                        if name == "--" or not name.strip():
                            try:
                                from sys_utils import resolve_stock_name
                                name = resolve_stock_name(code_str)
                            except Exception:
                                name = "--"
                        pct_val = row.get("percent", 0.0)
                        if pd.notna(pct_val):
                            try:
                                pct = float(str(pct_val).replace('%', ''))
                            except ValueError:
                                pct = 0.0
                        
                        price_val = row.get("price", 0.0)
                        if pd.notna(price_val):
                            try:
                                price = float(price_val)
                            except ValueError:
                                price = 0.0
                        
                        rank_val_raw = row.get("rank", 0)
                        if pd.notna(rank_val_raw):
                            try:
                                rank_val = int(float(rank_val_raw))
                            except ValueError:
                                rank_val = 0
                        
                        dff2_val = row.get("dff2", row.get("dff", 0.0))
                        if pd.notna(dff2_val):
                            try:
                                dff2 = float(dff2_val)
                            except ValueError:
                                dff2 = 0.0

                        dff3_val = row.get("dff3", 0.0)
                        if pd.notna(dff3_val):
                            try:
                                dff3 = float(dff3_val)
                            except ValueError:
                                dff3 = 0.0
                    except Exception as parse_err:
                        service_logger.debug(f"解析历史数据 {code_str} 异常: {parse_err}")
                else:
                    try:
                        if isinstance(row, pd.DataFrame):
                            row = row.iloc[0]
                        if row is not None:
                            name = row.get("name", row.get("Name", "--"))
                            pct = float(row.get('percent', row.get('ratio', 0.0)))
                            price = float(row.get('trade', row.get('close', row.get('price', 0.0))))
                            rank_val = int(row.get('Rank', row.get('rank', 0)))
                            dff2 = float(row.get('dff2', row.get('DFF2', 0.0)))
                            dff3 = float(row.get('dff3', row.get('DFF3', 0.0)))
                    except Exception:
                        pass

                # 补齐个股名称兜底解析
                if name == "--" or not name.strip():
                    try:
                        from sys_utils import resolve_stock_name
                        name = resolve_stock_name(code_str)
                    except Exception:
                        name = "--"

                # 从 quotes 缓存兜底个股名称等
                if name == "--" and hasattr(self, '_last_data_cache') and self._last_data_cache:
                    q_data = self._last_data_cache.get("quotes", {})
                    if code_str in q_data:
                        name = q_data[code_str].get("name", name)
                        if not is_history_mode:
                            pct = q_data[code_str].get("percent", pct)
                            price = q_data[code_str].get("price", price)

                # 动态获取自定义列值
                extra_vals = {}
                for ec in extra_cols:
                    val_item = "--"
                    try:
                        if row is not None:
                            val_item = safe_str(row.get(ec))
                    except Exception:
                        pass
                    extra_vals[ec] = val_item

                matched_stocks.append({
                    "code": code_str,
                    "name": name,
                    "val": pct,
                    "price": price,
                    "dff2": dff2,
                    "dff3": dff3,
                    "rank": rank_val,
                    "extra_vals": extra_vals
                })

        if not matched_stocks:
            messagebox.showinfo("信息", f"板块【{target_concept}】暂无匹配的人气个股", parent=self.root)
            return

        # 默认按涨幅降序
        matched_stocks.sort(key=lambda x: x["val"], reverse=True)

        # 3. 销毁并重建 Toplevel 窗口（自愈并适配动态列头）
        geo = self.config.get("concept_window_geometry", "600x385")
        if getattr(self, "concept_win", None) is not None and self.concept_win.winfo_exists():
            try:
                geo = self.concept_win.winfo_geometry()
            except Exception:
                pass
            self.concept_win.destroy()

        win = tk.Toplevel(self.root)
        self.concept_win = win
        try:
            win.geometry(geo)
        except Exception:
            win.geometry("600x385")
            
        # 监听大小与坐标变化以保存布局
        def _save_concept_win_geo(event):
            if win.winfo_exists():
                try:
                    self.config["concept_window_geometry"] = win.winfo_geometry()
                except Exception:
                    pass
        win.bind("<Configure>", _save_concept_win_geo)
        win.bind("<Escape>", lambda e: win.destroy())
        
        # 4. 创建内部布局 （包含 1px 边框与极窄滚动条）
        frame = tk.Frame(win, bg="white", highlightbackground="#CCCCCC", highlightthickness=1, bd=0)
        frame.pack(fill="both", expand=True, padx=4, pady=4)

        # 自适应列构成：基础列 + 配置的自定义列 (完全对齐人气排行)
        columns = ["idx", "code", "name", "val", "price", "dff2", "dff3", "rank"] + list(extra_cols)
        col_texts = {
            "idx": "序号",
            "code": "代码",
            "name": "名称",
            "val": "涨幅(%)",
            "price": "最新",
            "dff2": "dff2",
            "dff3": "dff3",
            "rank": "Rank"
        }

        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", style="Treeview")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="Slim.Vertical.TScrollbar")
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 5. 排序自适应及与人气视图一致的功能
        def sort_top10_column(t, col, reverse):
            self.sort_column(t, col, reverse)
            # 点击后 toggle
            t.heading(col, command=lambda c=col: sort_top10_column(t, c, not reverse))

        for col in columns:
            tree.heading(col, text=col_texts.get(col, col), command=lambda c=col: sort_top10_column(tree, c, False))
            if col == "idx":
                width = 26
                stretch = False
            elif col == "code":
                width = 52
                stretch = False
            elif col == "name":
                width = 64
                stretch = True
            elif col == "val":
                width = 48
                stretch = True
            elif col == "price":
                width = 50
                stretch = True
            elif col == "dff2":
                width = 44
                stretch = True
            elif col == "dff3":
                width = 44
                stretch = True
            elif col == "rank":
                width = 40
                stretch = True
            else:
                width = 48  # 自定义追加列的默认宽度
                stretch = True
            tree.column(col, anchor="center", width=width, stretch=stretch)

        tree.tag_configure("up",       foreground="#E02020", font=("Microsoft YaHei", 9, "bold"))
        tree.tag_configure("down",     foreground="#20A020", font=("Microsoft YaHei", 9, "bold"))
        tree.tag_configure("flat",     foreground="#000000", font=("Microsoft YaHei", 9))
        tree.tag_configure("favorite", background="#e6ffe6", font=("Microsoft YaHei", 9, "bold"))

        self.concept_tree = tree

        # 单击与双击联动事件
        def on_select_top10(event):
            if getattr(self, '_is_scrolling_to_code', False):
                return
            self._last_active_tree = tree
            sel = tree.selection()
            if sel:
                vals = tree.item(sel[0], "values")
                if vals and len(vals) >= 2:
                    code = str(vals[1]).strip().zfill(6) # 0 is idx, 1 is code
                    if getattr(self, '_active_link_code', None) == code:
                        return
                    self.tree_scroll_to_code(code, vis=True)

        def on_double_click_top10(event):
            sel = tree.selection()
            if sel:
                vals = tree.item(sel[0], "values")
                if vals and len(vals) >= 3:
                    code = str(vals[1]).strip().zfill(6) # 0 is idx, 1 is code
                    name = str(vals[2]).strip()          # 2 is name
                    if name.startswith("★ "):
                        name = name[len("★ "):]
                    
                    block = getattr(self, '_block_cache', {}).get(code, '--')
                    messagebox.showinfo("板块信息", f"个股: {name} ({code})\n所属行业板块: {block}", parent=self.concept_win)

        tree.bind("<<TreeviewSelect>>", on_select_top10)
        tree.bind("<Double-1>", on_double_click_top10)
        tree.bind("<Button-3>", self.show_context_menu)
        tree.bind("<Control-c>", self.on_copy_shortcut)
        tree.bind("<Control-C>", self.on_copy_shortcut)

        win.title(f"板块【{target_concept}】个股列表")
        
        # 插入匹配的股票行
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()

        for idx, item in enumerate(matched_stocks):
            code_str = item["code"]
            name = item["name"]
            is_fav = code_str in fav_stocks
            display_name = f"★ {name}" if is_fav else name

            percent = item["val"]
            price = item["price"]
            dff2 = item["dff2"]
            dff3 = item["dff3"]
            rank_val = item["rank"]

            tag = "flat"
            if percent > 0:
                tag = "up"
            elif percent < 0:
                tag = "down"

            tags = [tag]
            if is_fav:
                tags.append("favorite")

            percent_str = f"{percent:+.2f}" if percent > 0 else (f"{percent:.2f}" if percent < 0 else "0.00")
            price_str = f"{price:.2f}" if isinstance(price, (int, float)) else str(price)
            dff2_str = f"{dff2:.1f}" if isinstance(dff2, (int, float)) else str(dff2)
            dff3_str = f"{dff3:.1f}" if isinstance(dff3, (int, float)) else str(dff3)
            rank_str = str(rank_val)

            row_values = (
                idx + 1,
                code_str,
                display_name,
                percent_str,
                price_str,
                dff2_str,
                dff3_str,
                rank_str
            )
            # 自定义列的值动态追加到元组中
            extra_vals = item.get("extra_vals", {})
            for ec in extra_cols:
                row_values = row_values + (extra_vals.get(ec, "--"),)

            tree.insert("", "end", values=row_values, tags=tuple(tags))

        # 6. 同步人气主窗口的排序列和升降序
        main_sort_col = getattr(self.tree_res, "sort_col", self.config.get("sort_col", "val"))
        if main_sort_col == "percent":
            main_sort_col = "val"
        main_sort_descending = getattr(self.tree_res, "sort_descending", self.config.get("sort_descending", True))
        if main_sort_col in columns:
            sort_top10_column(tree, main_sort_col, main_sort_descending)

        # 7. 在底部添加统计信息框
        stat_frame = tk.Frame(win, bg="#F9F9F9", height=24)
        stat_frame.pack(side="bottom", fill="x", padx=4, pady=2)

        up_stocks = [x for x in matched_stocks if x["val"] > 0]
        down_stocks = [x for x in matched_stocks if x["val"] < 0]
        flat_stocks = [x for x in matched_stocks if x["val"] == 0]

        avg_up = sum(x["val"] for x in up_stocks) / len(up_stocks) if up_stocks else 0.0
        avg_down = sum(x["val"] for x in down_stocks) / len(down_stocks) if down_stocks else 0.0

        stat_text = f" 统计: 上涨 {len(up_stocks)}只 (均幅 {avg_up:+.2f}%) | 下跌 {len(down_stocks)}只 (均幅 {avg_down:+.2f}%) | 平盘 {len(flat_stocks)}只"
        lbl_stat = tk.Label(stat_frame, text=stat_text, font=("Microsoft YaHei", 9, "bold"), fg="#333333", bg="#F9F9F9", anchor="w")
        lbl_stat.pack(side="left", padx=6, pady=2)

        win.deiconify()
        win.lift()
        win.focus_force()

if __name__ == "__main__":
    # Windows/PyInstaller 多进程兼容性支持
    import multiprocessing
    multiprocessing.freeze_support()
    
    root = tk.Tk()
    app = PRServiceGUI(root)
    root.mainloop()
