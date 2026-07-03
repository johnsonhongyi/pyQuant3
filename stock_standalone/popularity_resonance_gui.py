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
        self.current_date = time.strftime("%Y-%m-%d")
        
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

        # 初始化通用 IPC 行情同步管理器 (通用框架)
        self.sync_manager = IPCSyncManager(
            port=26671,
            data_callback=self.on_realtime_data_updated,
            logger=service_logger
        )
        self.sync_manager.start()
        
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
        if hasattr(self, 'root'):
            self.root.after(5000, self._check_auto_refresh_after_close)

    def on_close(self):
        try:
            self.sync_manager.stop()
        except Exception:
            pass
        self.save_config_settings()
        
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

    def _adjust_tree_column_widths(self, tree):
        try:
            # 1. 确保 Treeview 已经有了实际分配的宽度
            total_width = tree.winfo_width()
            if total_width <= 50:
                return
            
            # 2. 扣除滚动条的宽度（固定扣除 18 像素）
            usable_width = total_width - 18
            if usable_width <= 50:
                return

            # 3. 找出展示中的列
            display_cols = tree.cget("displaycolumns")
            if not display_cols or display_cols == ("#all",) or display_cols == "":
                display_cols = tree.cget("columns")
            
            display_cols = list(display_cols)
            
            # 4. 计算固定列和可拉伸列宽度
            fixed_cols = []
            stretch_cols = []
            
            for col in display_cols:
                col_info = tree.column(col)
                if col_info.get("stretch", True) and col not in ("idx", "code"):
                    stretch_cols.append(col)
                else:
                    fixed_cols.append((col, col_info.get("width", 50)))
            
            fixed_width = 0
            for col, w in fixed_cols:
                fixed_width += w
                
            remaining_width = usable_width - fixed_width
            if remaining_width <= 20:
                # 剩余空间过窄时，强制拉伸列维持最小宽度为 30
                min_w = 30
                for col in stretch_cols:
                    tree.column(col, width=min_w)
                return
                
            # 5. 将剩余宽度平均分配给可拉伸列
            if stretch_cols:
                allocated_w = int(remaining_width / len(stretch_cols))
                if allocated_w < 30:
                    allocated_w = 30
                for col in stretch_cols:
                    tree.column(col, width=allocated_w)
        except Exception as e:
            service_logger.error(f"Adjust tree column widths failed: {e}")

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
            "高送转", "含可转债", "国家队持股", "地方政府平台", "央企控股", "军工改革"
        }
        if name_str in NOISE_CONCEPTS:
            return True
        for keyword in ("改革", "股通", "成指", "重仓", "持股", "中字头", "融资", "昨日", "送转", "转债", "指数", "成分"):
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
        if not values or len(values) < 3:
            return
            
        code = str(values[1]).strip().zfill(6)
        name = str(values[2]).strip()
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

        # [NEW] 查找此个股所属的最强板块（股票只数最多）并支持右键一键打开
        block_str = getattr(self, '_block_cache', {}).get(code, "")
        if block_str and block_str not in ("--", "nan", "None"):
            import re
            cats = [c.strip() for c in re.split(r'[;；,，/|]', block_str) if c.strip()]
            if cats:
                scores_dict = getattr(self, "_all_concept_scores", {})
                
                def get_cat_strength(cat_name):
                    norm_cat = self._normalize_concept_name(cat_name)
                    max_c = 0
                    for k, count in scores_dict.items():
                        if self._normalize_concept_name(k) == norm_cat:
                            max_c = max(max_c, count)
                    return max_c
                
                # 双重优先级排序：非低优先级(0)排前面，低优先级(1)排后面；在此基础上按强度（只数）降序排列
                cats.sort(key=lambda c: (1 if self._is_noise_concept(c) else 0, -get_cat_strength(c)))
                
                # 获取前 3 个最强的实际意义板块并动态展示
                top3_cats = cats[:3]
                for strongest_cat in top3_cats:
                    strength_num = get_cat_strength(strongest_cat)
                    menu.add_command(
                        label=f"📂 查看最强板块个股 ({strongest_cat}:{strength_num}只)", 
                        command=lambda name=strongest_cat: self.show_concept_top10_window(name)
                    )
                menu.add_separator()

        if not is_fav:
            menu.add_command(label=f"★ 添加重点关注 ({name})", command=lambda: self.add_to_favorites(code))
        else:
            menu.add_command(label=f"☆ 取消重点关注 ({name})", command=lambda: self.remove_from_favorites(code))
            
        menu.post(event.x_root, event.y_root)

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

    def on_realtime_data_updated(self, df):
        """当主程序通过 Socket 推送最新的 DataFrame 时的回调"""
        self.root.after(0, lambda: self.refresh_realtime_fields(df))

    def refresh_realtime_fields(self, df=None):
        # 核心防御：若当前查看的并非今天的数据（处于历史复盘状态），直接拦截并忽略实时行情的渲染和板块统计更新，防止历史数据被覆盖
        today = time.strftime("%Y-%m-%d")
        current_view_date = self.date_entry.get().strip() if hasattr(self, "date_entry") else today
        if current_view_date != today:
            return

        if df is None:
            df = self.sync_manager.get_current_df()
        if df is None or df.empty:
            return

        _, _, _extra_cols = self._get_all_cols()
        BASE_UPDATE_COUNT = 8  # idx/code/name/val/price/dff2/dff3/rank

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

                        new_vals[3] = f"{pct:.2f}"
                        new_vals[4] = price_str
                        new_vals[5] = f"{dff2:.1f}"
                        new_vals[6] = f"{dff3:.1f}"
                        new_vals[7] = str(rank)

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
                                    try:
                                        new_vals[idx_in_vals] = f"{float(v):.2f}"
                                    except (ValueError, TypeError):
                                        new_vals[idx_in_vals] = str(v)
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
                    all_stocks_for_stats[code_str] = {
                        "percent": pct,
                        "category": block_str,
                        "close": price_str,
                        "ma5d": row.get('ma5d', 0.0) if row is not None else 0.0,
                        "ma20d": row.get('ma20d', 0.0) if row is not None else 0.0,
                        "ma60d": row.get('ma60d', 0.0) if row is not None else 0.0,
                    }

        # 实时根据推送的行情重新分析和更新板块排行展示
        if all_stocks_for_stats:
            self.update_concept_ranking(all_stocks_for_stats)

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
        
    def _get_dpi_scale_factor(self):
        try:
            return self.root.winfo_fpixels('1i') / 96.0
        except Exception:
            return 1.0

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
                
            # 保存 sash 比例
            if hasattr(self, "paned") and hasattr(self, "sash_restored") and self.sash_restored:
                try:
                    pos = self.paned.sash_coord(0)[0]
                    if pos > 50:
                        width = self.paned.winfo_width()
                        if width > 100 and pos < width - 50:
                            self.config["sash_ratio"] = float(pos) / float(width)
                except Exception as e:
                    service_logger.error(f"Failed to save sash in config: {e}")

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except:
            pass

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

        # 主显示区域 (左右分栏)
        main_pane = tk.Frame(self.root)
        main_pane.pack(fill="both", expand=True, padx=4, pady=2)

        # 引入中间垂直分隔的手动拖动
        self.paned = tk.PanedWindow(main_pane, orient="horizontal", sashrelief="raised", sashwidth=4)
        self.paned.pack(fill="both", expand=True)

        self.sash_restored = False

        # 左分栏
        self.left_frame = tk.Frame(self.paned)
        self.paned.add(self.left_frame, minsize=200)

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
        self.paned.add(self.right_frame, minsize=300)

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

        self._last_paned_width = 0

        # 设置 sash 的位置恢复与保存
        def save_sash_pos(event=None):
            if not self.sash_restored:
                return
            try:
                pos = self.paned.sash_coord(0)[0]
                if pos <= 50:
                    return
                width = self.paned.winfo_width()
                if width > 100 and pos < width - 50:
                    ratio = float(pos) / float(width)
                    self.config["sash_ratio"] = ratio
                    self.save_config_settings()
                    service_logger.debug(f"[sash] 已保存 PR 界面 sash_ratio={ratio:.4f}")
            except Exception as e:
                service_logger.error(f"Failed to save sash position: {e}")

        def restore_sash(event=None):
            width = self.paned.winfo_width()
            if width > 100:  # 确保已经分配合理的大小
                # 只有在初次还原，或者宽度发生变化时，才按比例重置
                if not self.sash_restored or abs(width - getattr(self, '_last_paned_width', 0)) > 2:
                    self._last_paned_width = width
                    ratio = self.config.get("sash_ratio", 380.0 / 780.0)
                    target_sash = int(width * ratio)
                    try:
                        self.paned.sash_place(0, target_sash, 0)
                        self.sash_restored = True
                    except Exception:
                        pass

        self.paned.bind("<Configure>", restore_sash)
        self.root.after(200, restore_sash)  # 兜底延迟执行
        self.paned.bind("<ButtonRelease-1>", save_sash_pos)

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

    # ── 固定基础列（block 已移除，通过 _block_cache 字典存储，双击查询）──
    _BASE_FIXED_COLS = ("idx", "code", "name", "val", "price", "dff2", "dff3", "rank")
    _BASE_HEADERS = {
        "idx":   "",            # 由 first_col_title 动态填充
        "code":  "代码",
        "name":  "名称",
        "val":   "涨",          # 花标签时改为"涨幅"
        "price": "最新",
        "dff2":  "dff2",
        "dff3":  "dff3",
        "rank":  "Rank",
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
        tree.heading("idx",   text=first_col_title)
        tree.heading("code",  text="代码")
        tree.heading("name",  text="名称")
        tree.heading("val",   text="涨幅" if first_col_title == "花" else "涨")
        tree.heading("price", text="最新")
        tree.heading("dff2",  text="dff2")
        tree.heading("dff3",  text="dff3")
        tree.heading("rank",  text="Rank")

        # 基础列宽
        tree.column("idx",   width=26, anchor="center", stretch=False)
        tree.column("code",  width=52, anchor="center", stretch=False)
        tree.column("name",  width=64, anchor="center", stretch=True)
        tree.column("val",   width=48, anchor="center", stretch=True)
        tree.column("price", width=50, anchor="center", stretch=True)
        tree.column("dff2",  width=44, anchor="center", stretch=True)
        tree.column("dff3",  width=44, anchor="center", stretch=True)
        tree.column("rank",  width=40, anchor="center", stretch=True)

        # 追加自定义列的表头与列宽
        for ec in extra_cols:
            tree.heading(ec, text=ec)
            tree.column(ec, width=48, anchor="center", stretch=True)

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

        # 绑定大小改变事件以自适应列宽
        tree.bind("<Configure>", lambda e, t=tree: self._adjust_tree_column_widths(t))

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
                        mapping = {
                            "val": "percent",
                            "dff2": "dff",
                            "dff3": "dff"
                        }
                        target_col = mapping.get(col, col)
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
                "code": "代码",
                "name": "名称",
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
        # 手动查询刷新，传入 force_save=True 以强制持久化数据
        threading.Thread(target=self._run_once_job, args=(True,), daemon=True).start()

    def _run_once_job(self, force_save=False):
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
                        "timestamp": time.time(),
                        "block_cache": getattr(self, "_block_cache", {})
                    }
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, indent=4, ensure_ascii=False)
                except Exception as cache_err:
                    service_logger.error(f"写入数据缓存失败: {cache_err}")
            
            # 每日数据持久化更新当日数据 (在 save_daily_resonance_csv 内部自适应校验交易日)
            self.save_daily_resonance_csv(em_data, ths_data, lh_data, tgb_data, resonance_results[:limit], all_quotes, force_save=force_save)
            
            # 5. 在主线程中安全地更新所有表（仅在当前查看的是今天的数据时更新界面，防止覆盖历史复盘视图）
            today = time.strftime("%Y-%m-%d")
            current_view_date = self.date_entry.get().strip() if hasattr(self, "date_entry") else today
            if current_view_date == today:
                self.root.after(0, lambda: self.update_all_tables(em_data, ths_data, lh_data, tgb_data, resonance_results[:limit], all_quotes))
            else:
                service_logger.info(f"后台自动更新了今日数据，因当前正处于历史数据({current_view_date})复盘模式，跳过界面重绘。")
            
        except Exception as e:
            self.root.after(0, lambda: self.lbl_status.config(text=f"刷新失败: {e}", fg="red"))
        finally:
            self.root.after(0, lambda: self.btn_refresh.config(state="normal", text="查询刷新"))

    def update_all_tables(self, em_data, ths_data, lh_data, tgb_data, resonance_results, quotes):
        # 缓存最新传入的数据，用于点击概念过滤时重新渲染
        self._last_data_cache = {
            "em_data": em_data,
            "ths_data": ths_data,
            "lh_data": lh_data,
            "tgb_data": tgb_data,
            "resonance_results": resonance_results,
            "quotes": quotes
        }

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
                        try:
                            result.append(f"{float(v):.2f}")
                        except (ValueError, TypeError):
                            result.append(str(v))
                except Exception:
                    result.append("--")
            return tuple(result)

        # 2. 定义带去重功能的单个表格填充辅助函数
        def populate(tree, data_dict):
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
                if block_str == '--' or not block_str:
                    block_str = self._block_cache.get(code_str, '--')

                tag = "flat"
                if pct > 0:
                    tag = "up"
                elif pct < 0:
                    tag = "down"

                code_str = str(code).strip().zfill(6)
                is_fav = code_str in fav_stocks
                display_name = f"★ {name}" if is_fav else name
                tags = [tag]
                if is_fav:
                    tags.append("favorite")

                # 板块写入缓存，不写入 Treeview
                if block_str and block_str not in ('--', 'nan', 'None'):
                    self._block_cache[code_str] = block_str
                    # 放入统计字典
                    all_stocks_for_stats[code_str] = {
                        "percent": pct,
                        "category": block_str,
                        "close": price_str,
                        "ma5d": row_obj.get('ma5d', 0.0) if row_obj is not None else 0.0,
                        "ma20d": row_obj.get('ma20d', 0.0) if row_obj is not None else 0.0,
                        "ma60d": row_obj.get('ma60d', 0.0) if row_obj is not None else 0.0,
                    }

                # 概念过滤
                if getattr(self, 'selected_concept', None) is not None:
                    import re
                    cats = [c.strip() for c in re.split(r'[;；,，/|]', block_str) if c.strip()]
                    if self.selected_concept not in cats:
                        continue

                # 基础列 + 自定义追加列
                extra_vals = _read_extra_vals(row_obj)
                row_values = (display_rank, code, display_name, f"{pct:.2f}",
                              price_str, dff2_str, dff3_str, rank_str) + extra_vals
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
            if block_str == '--' or not block_str:
                block_str = self._block_cache.get(code_str, '--')

            tag = "flat"
            if pct > 0:
                tag = "up"
            elif pct < 0:
                tag = "down"

            code_str = str(code).strip().zfill(6)
            is_fav = code_str in fav_stocks
            display_name = f"★ {name}" if is_fav else name
            tags = [tag]
            if is_fav:
                tags.append("favorite")

            # 板块写入缓存，不写入 Treeview
            if block_str and block_str not in ('--', 'nan', 'None'):
                self._block_cache[code_str] = block_str
                # 放入统计字典
                all_stocks_for_stats[code_str] = {
                    "percent": pct,
                    "category": block_str,
                    "close": price_str,
                    "ma5d": row_obj_res.get('ma5d', 0.0) if row_obj_res is not None else 0.0,
                    "ma20d": row_obj_res.get('ma20d', 0.0) if row_obj_res is not None else 0.0,
                    "ma60d": row_obj_res.get('ma60d', 0.0) if row_obj_res is not None else 0.0,
                }

            # 概念过滤
            if getattr(self, 'selected_concept', None) is not None:
                import re
                cats = [c.strip() for c in re.split(r'[;；,，/|]', block_str) if c.strip()]
                if self.selected_concept not in cats:
                    continue

            # 共振表同样追加自定义列
            extra_vals_res = _read_extra_vals(row_obj_res)
            row_values_res = (rank, code, display_name, f"{pct:.2f}",
                              price_str, dff2_str, dff3_str, rank_str) + extra_vals_res
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

            # 追加或保留板块缓存（历史数据也要支持双击查板块）
            if not hasattr(self, "_block_cache") or self._block_cache is None:
                self._block_cache = {}
            # 用于统计前 10 概念热度的个股信息收集字典
            all_stocks_for_stats = {}

            # 获取当前配置的自定义追加列
            _, _, _extra_cols = self._get_all_cols()
            # 检测 CSV 中实际存在哪些自定义列（旧文件可能没有）
            csv_cols = set(df.columns.tolist())
            available_extra = [c for c in _extra_cols if c in csv_cols]

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
                code = str(row.get("code", "")).strip().zfill(6)
                name = safe_str(row.get("name"), default="--")

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
                        "percent": pct_val,
                        "category": block,
                        "close": price,
                        "ma5d": 0.0,
                        "ma20d": 0.0,
                        "ma60d": 0.0
                    }

                # 读取自定义列值（CSV 中有则取，否则 '--'）
                extra_vals = tuple(safe_str(row.get(c)) for c in _extra_cols)

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
            
            if not has_persisted:
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
                        # 冷却时间：至少间隔 5 分钟（300秒）才重试一次，防止异常时高频请求
                        import time as t_mod
                        now_ts = t_mod.time()
                        last_attempt = getattr(self, '_last_auto_save_attempt_time', 0.0)
                        fail_count = getattr(self, '_auto_save_fail_count', 0)
                        
                        if now_ts - last_attempt >= 300.0:
                            if not getattr(self, '_is_auto_saving_after_close', False):
                                self._is_auto_saving_after_close = True
                                self._last_auto_save_attempt_time = now_ts
                                service_logger.info(f"检测到收盘（15:15后）且今日人气共振数据尚未持久化，启动自动刷新与持久化 (尝试次数: {fail_count + 1})...")
                                
                                def auto_job():
                                    try:
                                        self.root.after(0, lambda: self.lbl_status.config(text="自动同步数据中...", fg="blue"))
                                        # 自动查询并强制持久化数据
                                        self._run_once_job(force_save=True)
                                        # 延迟检测文件是否成功写入
                                        t_mod.sleep(5.0)
                                        if os.path.exists(gz_path) or os.path.exists(csv_path):
                                            self._auto_save_fail_count = 0
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
                # 每 30 分钟轮询检测一次状态
                self.root.after(1800000, self._check_auto_refresh_after_close)
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
            cat_str = info["category"]
            if not cat_str or cat_str in ("--", "nan", "None"):
                continue
            cats = [c.strip() for c in re.split(r'[;；,，/|]', cat_str) if c.strip()]
            pct = info["percent"]
            
            # 获取个股的基本属性
            name = info.get("name", "--")
            if name == "--" and hasattr(self, '_last_data_cache') and self._last_data_cache:
                q_data = self._last_data_cache.get("quotes", {})
                if code in q_data:
                    name = q_data[code].get("name", name)
            
            try:
                close = float(info["close"])
                ma5 = float(info["ma5d"])
                ma20 = float(info["ma20d"])
                ma6 = float(info["ma60d"])
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
            avg_pct = sum(percents) / len(percents)
            bullish_list = concept_is_bullish.get(cat, [])
            bullish_ratio = sum(bullish_list) / len(bullish_list) if bullish_list else 0.0
            
            # 使用和 tk 一致的得分算法并放大10倍
            score = avg_pct * (1.0 + bullish_ratio) * 10.0
            
            concept_score.append({
                "name": cat,
                "score": round(score, 2),
                "avg_percent": round(avg_pct, 2),
                "count": len(percents),
                "bullish_ratio": round(bullish_ratio, 2)
            })

        # 双重关键字排序：有价值明确概念的（is_noise为0）排前面，非清晰宏观概念（is_noise为1）排后面；同分类内按 count 只数降序排列
        concept_score.sort(key=lambda x: (1 if self._is_noise_concept(x["name"]) else 0, -x["count"]))
        top5 = concept_score[:5]

        if not top5:
            lbl_empty = tk.Label(self.dynamic_concepts_frame, text="暂无板块数据", font=("Microsoft YaHei", 9, "bold"), fg="gray")
            lbl_empty.pack(side="left")
        else:
            # 动态生成各概念板块，点击直接弹出二级 Constituents 弹窗，并提供视觉悬浮微动画
            for item in top5:
                c_name = item['name']
                c_count = item['count']
                
                lbl_c = tk.Label(
                    self.dynamic_concepts_frame,
                    text=f"{c_name}:{c_count}",
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
        main_sort_col = getattr(self.tree_res, "sort_col", self.config.get("sort_col", "percent"))
        main_sort_descending = getattr(self.tree_res, "sort_descending", self.config.get("sort_descending", True))
        
        # 将主排序列名映射为 5 元组的索引
        col_to_idx = {
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
        """点击详情中个股标签，实现联动"""
        self._update_detail_selection(idx)
        # 联动逻辑
        is_tdx = self.link_tdx_var.get()
        is_ths = self.link_ths_var.get()
        if is_tdx or is_ths:
            flags = {'tdx': is_tdx, 'ths': is_ths, 'dfcf': False}
            if get_link_manager:
                get_link_manager().push(code, flags=flags)
            elif self.local_sender:
                self.local_sender.send(code)
        if self.link_vis_var.get():
            threading.Thread(target=self.send_to_visualizer, args=(code,), daemon=True).start()
        self.lbl_status.config(text=f"已联动: {code}", fg="darkgreen")

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
        _, _, extra_cols = self._get_all_cols()
        
        # 收集所有人气排行中包含此概念的个股
        matched_stocks = []

        def safe_str(val, default="--"):
            if pd.isna(val) or str(val).strip().lower() in ('nan', 'none', ''):
                return default
            return str(val).strip()

        for code_str, block_str in getattr(self, '_block_cache', {}).items():
            cats = [c.strip() for c in re.split(r'[;；,，/|]', block_str) if c.strip()]
            cats_normalized = [self._normalize_concept_name(c) for c in cats]
            
            if target_concept in cats_normalized:
                name = "--"
                pct = 0.0
                price = 0.0
                rank_val = 0
                dff = 0.0
                volume = 0.0
                red = 0
                win_val = 0

                # 优先从历史缓存的 DataFrame 读取
                history_row = None
                if is_history_mode and hasattr(self, "_history_df") and self._history_df is not None:
                    try:
                        df_hist = self._history_df
                        # 强转并正确剔除浮点数带来的 .0$ 后缀，zfill(6) 对齐
                        matched_rows = df_hist[df_hist['code'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).str.zfill(6) == code_str]
                        if not matched_rows.empty:
                            history_row = matched_rows.iloc[0]
                    except Exception as ex:
                        service_logger.debug(f"从历史DF查找 {code_str} 异常: {ex}")

                # 读取属性
                if is_history_mode and history_row is not None:
                    try:
                        name = safe_str(history_row.get("name"))
                        pct_val = history_row.get("percent", 0.0)
                        if pd.notna(pct_val):
                            try:
                                pct = float(str(pct_val).replace('%', ''))
                            except ValueError:
                                pct = 0.0
                        
                        price_val = history_row.get("price", 0.0)
                        if pd.notna(price_val):
                            try:
                                price = float(price_val)
                            except ValueError:
                                price = 0.0
                        
                        rank_val_raw = history_row.get("rank", 0)
                        if pd.notna(rank_val_raw):
                            try:
                                rank_val = int(float(rank_val_raw))
                            except ValueError:
                                rank_val = 0
                        
                        dff2_val = history_row.get("dff2", history_row.get("dff", 0.0))
                        if pd.notna(dff2_val):
                            try:
                                dff = float(dff2_val)
                            except ValueError:
                                dff = 0.0

                        vol_val = history_row.get("volume", history_row.get("vol", 0.0))
                        if pd.notna(vol_val):
                            try:
                                volume = float(vol_val)
                            except ValueError:
                                volume = 0.0
                        
                        red = int(float(history_row.get("red", 0))) if pd.notna(history_row.get("red")) else 0
                        win_val = int(float(history_row.get("win", 0))) if pd.notna(history_row.get("win")) else 0
                    except Exception as parse_err:
                        service_logger.debug(f"解析历史数据 {code_str} 异常: {parse_err}")
                else:
                    # 实时模式
                    if df_all is not None and code_str in df_all.index:
                        try:
                            row = df_all.loc[code_str]
                            if isinstance(row, pd.DataFrame):
                                row = row.iloc[0]
                            name = row.get("name", row.get("Name", "--"))
                            pct = float(row.get('percent', row.get('ratio', 0.0)))
                            price = float(row.get('trade', row.get('close', row.get('price', 0.0))))
                            rank_val = int(row.get('Rank', row.get('rank', 0)))
                            dff = row.get('dff', row.get('DFF', 0.0))
                            volume = row.get('volume', row.get('vol', 0.0))
                            red = row.get('red', 0)
                            win_val = row.get('win', 0)
                        except Exception:
                            pass
                
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
                    val = "--"
                    if is_history_mode and history_row is not None:
                        val = safe_str(history_row.get(ec))
                    elif not is_history_mode and df_all is not None and code_str in df_all.index:
                        try:
                            row = df_all.loc[code_str]
                            if isinstance(row, pd.DataFrame):
                                row = row.iloc[0]
                            val = safe_str(row.get(ec))
                        except Exception:
                            pass
                    extra_vals[ec] = val

                matched_stocks.append({
                    "code": code_str,
                    "name": name,
                    "percent": pct,
                    "price": price,
                    "rank": rank_val,
                    "dff": dff,
                    "volume": volume,
                    "red": red,
                    "win": win_val,
                    "extra_vals": extra_vals
                })

        if not matched_stocks:
            messagebox.showinfo("信息", f"板块【{target_concept}】暂无匹配的人气个股", parent=self.root)
            return

        # 默认按涨幅降序
        matched_stocks.sort(key=lambda x: x["percent"], reverse=True)

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

        # 自适应列构成：基础列 + 配置的自定义列
        columns = ["code", "name", "rank", "percent", "dff", "volume", "red", "win"] + list(extra_cols)
        col_texts = {
            "code": "代码",
            "name": "名称",
            "rank": "Rank",
            "percent": "涨幅(%)",
            "dff": "dff",
            "volume": "成交量",
            "red": "连阳",
            "win": "主升"
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
            if col in ("name", "code"):
                width = 80
            elif col in ("rank", "percent", "dff", "volume", "red", "win"):
                width = 50
            else:
                width = 65  # 自定义追加列的默认宽度
            tree.column(col, anchor="center", width=width)

        tree.tag_configure("up",       foreground="#E02020", font=("Microsoft YaHei", 9, "bold"))
        tree.tag_configure("down",     foreground="#20A020", font=("Microsoft YaHei", 9, "bold"))
        tree.tag_configure("flat",     foreground="#000000", font=("Microsoft YaHei", 9))

        self.concept_tree = tree

        # 单击与双击联动事件
        def on_select_top10(event):
            sel = tree.selection()
            if sel:
                vals = tree.item(sel[0], "values")
                if vals and len(vals) >= 1:
                    code = str(vals[0]).strip().zfill(6)
                    # 联动
                    is_tdx = self.link_tdx_var.get()
                    is_ths = self.link_ths_var.get()
                    if is_tdx or is_ths:
                        flags = {'tdx': is_tdx, 'ths': is_ths, 'dfcf': False}
                        if get_link_manager:
                            get_link_manager().push(code, flags=flags)
                        elif self.local_sender:
                            self.local_sender.send(code)
                    if self.link_vis_var.get():
                        threading.Thread(target=self.send_to_visualizer, args=(code,), daemon=True).start()
                    self.lbl_status.config(text=f"已联动: {code}", fg="darkgreen")

        def on_double_click_top10(event):
            sel = tree.selection()
            if sel:
                vals = tree.item(sel[0], "values")
                if vals and len(vals) >= 2:
                    code = str(vals[0]).strip().zfill(6)
                    name = str(vals[1]).strip()
                    if name.startswith("★ "):
                        name = name[len("★ "):]
                    
                    block = getattr(self, '_block_cache', {}).get(code, '--')
                    messagebox.showinfo("板块信息", f"个股: {name} ({code})\n所属行业板块: {block}", parent=self.concept_win)

        tree.bind("<<TreeviewSelect>>", on_select_top10)
        tree.bind("<Double-1>", on_double_click_top10)

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

            percent = item["percent"]
            rank_val = item["rank"]
            dff = item["dff"]
            volume = item["volume"]
            red = item["red"]
            win_val = item["win"]

            tag = "flat"
            if percent > 0:
                tag = "up"
            elif percent < 0:
                tag = "down"

            row_values = (
                code_str,
                display_name,
                rank_val,
                f"{percent:.2f}",
                f"{dff:.1f}" if isinstance(dff, (int, float)) else str(dff),
                f"{volume:.1f}" if isinstance(volume, (int, float)) else str(volume),
                red,
                win_val
            )
            # 自定义列的值动态追加到元组中
            extra_vals = item.get("extra_vals", {})
            for ec in extra_cols:
                row_values = row_values + (extra_vals.get(ec, "--"),)

            tree.insert("", "end", values=row_values, tags=(tag,))

        # 6. 同步人气主窗口的排序列和升降序
        main_sort_col = getattr(self.tree_res, "sort_col", self.config.get("sort_col", "percent"))
        main_sort_descending = getattr(self.tree_res, "sort_descending", self.config.get("sort_descending", True))
        if main_sort_col in columns:
            sort_top10_column(tree, main_sort_col, main_sort_descending)

        # 7. 在底部添加统计信息框
        stat_frame = tk.Frame(win, bg="#F9F9F9", height=24)
        stat_frame.pack(side="bottom", fill="x", padx=4, pady=2)

        up_stocks = [x for x in matched_stocks if x["percent"] > 0]
        down_stocks = [x for x in matched_stocks if x["percent"] < 0]
        flat_stocks = [x for x in matched_stocks if x["percent"] == 0]

        avg_up = sum(x["percent"] for x in up_stocks) / len(up_stocks) if up_stocks else 0.0
        avg_down = sum(x["percent"] for x in down_stocks) / len(down_stocks) if down_stocks else 0.0

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
