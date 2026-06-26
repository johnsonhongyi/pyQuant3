# -*- coding:utf-8 -*-
from logger_utils import LoggerFactory
import logging
import traceback
import tkinter as tk
from tkinter import ttk
import pandas as pd
from typing import Any, Optional, Protocol, Union, runtime_checkable, TYPE_CHECKING

logger = LoggerFactory.getLogger("instock_TK.Treeview")

@runtime_checkable
class TreeviewAppProtocol(Protocol):
    """Protocol for StockMonitorApp to satisfy Pylance attribute checks in TreeviewMixin."""
    df_all: pd.DataFrame
    tree: ttk.Treeview
    current_cols: list[str]
    DISPLAY_COLS: list[str]
    dfcf_var: tk.BooleanVar
    _name_col_width: int
    _pending_cols: list[str]
    def get_scaled_value(self) -> float: ...
    def refresh_tree(self, df_sorted: Optional[pd.DataFrame] = None, force: bool = False) -> None: ...
    def bind_treeview_column_resize(self) -> None: ...

class TreeviewMixin:
    """Handles Treeview configuration, sorting, and data management."""
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
        df_all: pd.DataFrame
        tree: ttk.Treeview
        current_cols: list[str]
        DISPLAY_COLS: list[str]
        dfcf_var: tk.BooleanVar
        _name_col_width: int
        _pending_cols: list[str]
        def get_scaled_value(self) -> float: ...
        def refresh_tree(self, df_sorted: Optional[pd.DataFrame] = None, force: bool = False) -> None: ...
        def bind_treeview_column_resize(self) -> None: ...

    def _setup_tree_columns(self, tree: ttk.Treeview, cols: Union[list[str], tuple[str, ...]], sort_callback: Optional[Any] = None, other: dict[str, Any] = {}) -> None:
        """
        通用 Treeview 列初始化函数，优化宽度使其更紧凑
        """
        # 定义列宽分类
        # 极窄列
        co_narrow = ['ra', 'ral', 'fib', 'fibl', 'op', 'red', 'kind', 'win']
        # 中等窄列
        co_mid = ['trade', 'percent', 'per1d', 'perc1d', 'couts', 'boll', 'dff', 'df2', 'MainU']
        
        col_scaled = self.get_scaled_value() 

        # 列名中文化映射
        header_map = {
            'code': '代码', 'name': '名称', 'grade': '等级',
            'trade': '现价', 'percent': '涨幅', 'volume': '量比',
            'amount': '成交额', 'category': '行业/题材', 'emotion_status': '情绪状态'
        }

        for col in cols:
            header_text = header_map.get(col, col)
            if sort_callback:
                tree.heading(col, text=header_text, command=lambda _col=col: sort_callback(_col, False))
            else:
                tree.heading(col, text=header_text)
            
            # 基础拉伸设置为 True，除非特定列
            stretch = not getattr(self, 'dfcf_var', tk.BooleanVar(value=False)).get()

            if col == "code":
                width = int(80 * col_scaled)
                minwidth = int(60 * col_scaled)
                stretch = False
            elif col == "name":
                width = int(getattr(self, "_name_col_width", 120 * col_scaled))
                minwidth = int(90 * col_scaled)
                stretch = False
            elif col in co_narrow:
                width = int(45 * col_scaled)
                minwidth = int(30 * col_scaled)
            elif col == "emotion_status":
                width = int(100 * col_scaled)
                minwidth = int(80 * col_scaled)
            elif col == "emotion_baseline":
                width = int(60 * col_scaled)
                minwidth = int(45 * col_scaled)
            elif col in co_mid:
                width = int(55 * col_scaled)
                minwidth = int(40 * col_scaled)
            else:
                width = int(50 * col_scaled)
                minwidth = int(35 * col_scaled)
            tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=stretch)

    def update_treeview_cols(self, new_cols: list[str]) -> None:
        try:
            if not hasattr(self, 'df_all') or self.df_all is None or self.df_all.empty:
                logger.warning("⚠️ df_all为空,无法更新列配置")
                self._pending_cols = new_cols
                return
            
            valid_cols = [c for c in new_cols if c in self.df_all.columns]
            if not valid_cols:
                valid_cols = list(self.df_all.columns)[:5]
            
            if 'code' not in valid_cols and 'code' in self.df_all.columns:
                valid_cols = ["code"] + valid_cols
 
            if valid_cols == getattr(self, 'current_cols', []):
                return
 
            self.current_cols = valid_cols
            cols = tuple(self.current_cols)
            
            self.tree["displaycolumns"] = ()
            self.tree["columns"] = ()
            self.tree.update_idletasks()
 
            self.tree["columns"] = cols
            self.tree["displaycolumns"] = cols
            self.tree.configure(show="headings")
 
            self._setup_tree_columns(
                self.tree,
                cols,
                sort_callback=getattr(self, 'sort_by_column', None)
            )
 
            self.tree.after(100, lambda: self.refresh_tree(force=True) if hasattr(self, 'refresh_tree') else None)
            self.tree.after(500, lambda: getattr(self, 'bind_treeview_column_resize', lambda: None)())
            # 🔌 动态列订阅：通知后台进程 UI 需要的新列
            if hasattr(self, 'update_required_columns'):
                self.update_required_columns()
 
        except Exception as e:
            logger.error(f"❌ 更新 Treeview 列失败：{e}")
            traceback.print_exc()

    def sort_by_column(self, col: str, reverse: bool) -> None:
        """点击表头排序"""
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        # 尝试转为数字或优先级排序
        try:
            if col == 'name' and hasattr(self, 'feature_marker'):
                # ⚡ [PERF] 针对名称列，优先根据图标强度(水印)权重排序
                fm = getattr(self, 'feature_marker')
                # 返回 (权重分数, 原始文本) 二元组进行复合排序
                l.sort(key=lambda t: (fm.get_priority_score(t[0]), t[0]), reverse=reverse)
            elif col == 'MainU':
                # ⚡ [PERF] 针对 MainU 列，采用静态 LUT 进行 O(1) 高性能打分排序
                from mainu_sort import mainu_sort_score
                l.sort(key=lambda t: mainu_sort_score(t[0]), reverse=reverse)
            else:
                l.sort(key=lambda t: float(t[0].replace('%', '').replace('+', '')), reverse=reverse)
        except (ValueError, TypeError):
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        # 反转排序方向，以便下次点击
        self.tree.heading(col, command=lambda _col=col: self.sort_by_column(_col, not reverse))

    def refresh_tree_with_query(self, query_dict: dict[str, Any]) -> None:
        if not hasattr(self, 'df_all') or self.df_all.empty:
            return
        
        df = self.df_all.copy()
        display_cols = getattr(self, 'DISPLAY_COLS', [])
        
        if query_dict:
            for col, cond in query_dict.items():
                if col not in df.columns:
                    continue
                if isinstance(cond, str):
                    cond = cond.strip()
                    if '~' in cond:
                        try:
                            low, high = map(float, cond.split('~'))
                            df = df[(df[col] >= low) & (df[col] <= high)]
                        except: pass
                    elif cond.startswith(('>', '<', '>=', '<=', '==')):
                        df = df.query(f"{col}{cond}")
                    else:
                        df = df[df[col].astype(str).str.contains(cond)]
                else:
                    df = df[df[col] == cond]

        self.tree.delete(*self.tree.get_children())
        for idx, row in df.iterrows():
            values = [row.get(col, '') for col in display_cols]
            self.tree.insert("", "end", values=values)

    def _init_tree_sort_state(self, tree: ttk.Treeview) -> None:
        """初始化指定 Treeview 的多级排序属性"""
        if not hasattr(tree, 'sort_level1_col'):
            # 如果是主 Treeview，则尝试从 App 实例的属性进行对齐初始化，保持持久化一致
            if tree == getattr(self, 'tree', None):
                tree.sort_level1_col = getattr(self, 'sort_level1_col', None)
                tree.sort_level1_asc = getattr(self, 'sort_level1_asc', True)
                tree.sort_level2_col = getattr(self, 'sort_level2_col', None)
                tree.sort_level2_asc = getattr(self, 'sort_level2_asc', True)
                tree.sort_level3_col = getattr(self, 'sort_level3_col', None)
                tree.sort_level3_asc = getattr(self, 'sort_level3_asc', True)
                tree.sortby_col = getattr(self, 'sortby_col', None)
                tree.sortby_col_ascend = getattr(self, 'sortby_col_ascend', False)
            else:
                tree.sort_level1_col = None
                tree.sort_level1_asc = True
                tree.sort_level2_col = None
                tree.sort_level2_asc = True
                tree.sort_level3_col = None
                tree.sort_level3_asc = True
                tree.sortby_col = None
                tree.sortby_col_ascend = False

    def _save_mixin_ui_states(self, tree: ttk.Treeview) -> None:
        """多级排序发生改变时的保存状态分流处理器"""
        if tree != getattr(self, 'tree', None):
            self._last_active_concept_tree = tree
        # ⚡ [OPTIMIZE] 全局所有的多级排序都不要点击排序就写盘，全部存在内存内，在退出/关闭窗口或程序时统一写盘。
        # 这里不再主动调用 self.save_ui_states()以规避高频磁盘I/O。
        pass

    def _get_clean_header_text(self, tree: ttk.Treeview, col: str) -> str:
        """获取不含排序前缀的干净表头文字"""
        header_map = {
            'code': '代码', 'name': '名称', 'grade': '等级',
            'trade': '现价', 'percent': '涨幅', 'volume': '量比',
            'amount': '成交额', 'category': '行业/题材', 'emotion_status': '情绪状态',
            'zhuli_rank': '排名', 'change_pct': '涨幅%', 'win': '胜率', 'sum_perc': '盈亏%',
            'net_ratio': '主力净占比%', 'sector': '所属板块', 'hot_rank': '排名',
            'hot_tag': '标签', 'hot_reason': '深度推导逻辑', 'theme_date': '日期',
            'theme_name': '所属题材', 'theme_logic': '题材逻辑推演'
        }
        if col in header_map:
            return header_map[col]
            
        current_text = tree.heading(col, "text")
        clean_text = current_text
        clean_text = clean_text.replace("↑", "").replace("↓", "")
        clean_text = clean_text.replace("🔴[主]", "").replace("🟡[从]", "").replace("🟢[次]", "")
        return clean_text.strip()

    def update_mixin_tree_headers(self, tree: ttk.Treeview) -> None:
        """根据当前多级排序状态刷新指定 Treeview 的表头，并重新绑定排序命令"""
        self._init_tree_sort_state(tree)
        
        bound_cols = set()
        if tree.sort_level1_col:
            bound_cols.add(tree.sort_level1_col)
        if tree.sort_level2_col:
            bound_cols.add(tree.sort_level2_col)
        if tree.sort_level3_col:
            bound_cols.add(tree.sort_level3_col)

        cols = tree["columns"]
        for col in cols:
            text = self._get_clean_header_text(tree, col)
            is_multi = False
            col_asc = True
            
            if tree.sort_level1_col == col:
                col_asc = bool(tree.sort_level1_asc)
                text = f"🔴[主] {text}"
                is_multi = True
            elif tree.sort_level2_col == col:
                col_asc = bool(tree.sort_level2_asc)
                text = f"🟡[从] {text}"
                is_multi = True
            elif tree.sort_level3_col == col:
                col_asc = bool(tree.sort_level3_asc)
                text = f"🟢[次] {text}"
                is_multi = True
                
            # 动态从/次排序指示器
            if tree.sort_level1_col and col not in bound_cols:
                if tree.sortby_col == col:
                    bound_cnt = len(bound_cols)
                    if bound_cnt == 1:
                        text = f"🟡[从] {text}"
                    elif bound_cnt == 2:
                        text = f"🟢[次] {text}"
                    col_asc = bool(tree.sortby_col_ascend)
                    is_multi = True

            if is_multi or tree.sortby_col == col:
                arrow = "↑ " if col_asc else "↓ "
                text = arrow + text
                
            tree.heading(col, text=text, command=lambda _col=col: self.sort_mixin_by_column(tree, _col, self._get_mixin_current_col_asc(tree, _col)))

    def _get_mixin_current_col_asc(self, tree: ttk.Treeview, col: str) -> bool:
        """获取当前指定列的排序方向"""
        self._init_tree_sort_state(tree)
        if col == tree.sort_level1_col:
            return bool(tree.sort_level1_asc)
        elif col == tree.sort_level2_col:
            return bool(tree.sort_level2_asc)
        elif col == tree.sort_level3_col:
            return bool(tree.sort_level3_asc)
        # 如果是单排，且不是当前列，点击新列默认按降序排列(需要 reverse=True 才能让 sortby_col_ascend = not reverse = False)
        if tree.sortby_col != col:
            return True
        return bool(tree.sortby_col_ascend)

    def sort_mixin_by_column(self, tree: ttk.Treeview, col: str, reverse: bool) -> None:
        """左键点击表头时的核心多级排序状态处理与切换"""
        self._init_tree_sort_state(tree)
        
        is_multi_clicked = False
        if col == tree.sort_level1_col:
            tree.sort_level1_asc = not tree.sort_level1_asc
            is_multi_clicked = True
        elif col == tree.sort_level2_col:
            tree.sort_level2_asc = not tree.sort_level2_asc
            is_multi_clicked = True
        elif col == tree.sort_level3_col:
            tree.sort_level3_asc = not tree.sort_level3_asc
            is_multi_clicked = True
            
        if is_multi_clicked:
            # 同步到主 App 的属性（若是主 Tree）
            if tree == getattr(self, 'tree', None):
                self.sort_level1_asc = tree.sort_level1_asc
                self.sort_level2_asc = tree.sort_level2_asc
                self.sort_level3_asc = tree.sort_level3_asc
                
            self.update_mixin_tree_headers(tree)
            self.trigger_mixin_multi_level_sort(tree)
            self._save_mixin_ui_states(tree)
            return
            
        # 如果当前设置了主排序（L1），点击其他全新列头时，保留主排序，将其作为临时从/次排序
        if tree.sort_level1_col is not None:
            if tree.sortby_col == col:
                tree.sortby_col_ascend = not tree.sortby_col_ascend
            else:
                tree.sortby_col = col
                tree.sortby_col_ascend = not reverse
                
            if tree == getattr(self, 'tree', None):
                self.sortby_col = col
                self.sortby_col_ascend = tree.sortby_col_ascend
        else:
            # 一键自动解除所有多级排序，切回单列排序
            tree.sort_level1_col = None
            tree.sort_level2_col = None
            tree.sort_level3_col = None
            tree.sortby_col = col
            tree.sortby_col_ascend = not reverse
            
            if tree == getattr(self, 'tree', None):
                self.sort_level1_col = None
                self.sort_level2_col = None
                self.sort_level3_col = None
                self.sortby_col = col
                self.sortby_col_ascend = tree.sortby_col_ascend
                self.multi_sort_click_count = 0
            
        self.update_mixin_tree_headers(tree)
        self.trigger_mixin_multi_level_sort(tree)
        self._save_mixin_ui_states(tree)

    def set_mixin_multi_sort_level(self, tree: ttk.Treeview, col_name: str, level: int) -> None:
        """把某列设为指定的排序级别"""
        self._init_tree_sort_state(tree)
        
        if tree.sort_level1_col == col_name:
            tree.sort_level1_col = None
        if tree.sort_level2_col == col_name:
            tree.sort_level2_col = None
        if tree.sort_level3_col == col_name:
            tree.sort_level3_col = None

        if level == 1:
            tree.sort_level1_col = col_name
            tree.sort_level1_asc = True
        elif level == 2:
            tree.sort_level2_col = col_name
            tree.sort_level2_asc = True
        elif level == 3:
            tree.sort_level3_col = col_name
            tree.sort_level3_asc = True

        if tree == getattr(self, 'tree', None):
            self.sort_level1_col = tree.sort_level1_col
            self.sort_level1_asc = tree.sort_level1_asc
            self.sort_level2_col = tree.sort_level2_col
            self.sort_level2_asc = tree.sort_level2_asc
            self.sort_level3_col = tree.sort_level3_col
            self.sort_level3_asc = tree.sort_level3_asc
            self.multi_sort_click_count = 1 if level == 1 else getattr(self, 'multi_sort_click_count', 0)

        self.update_mixin_tree_headers(tree)
        self.trigger_mixin_multi_level_sort(tree)
        self._save_mixin_ui_states(tree)

    def clear_mixin_multi_sort_level(self, tree: ttk.Treeview, col_name: str) -> None:
        """取消某列的多级排序设置"""
        self._init_tree_sort_state(tree)

        if tree.sort_level1_col == col_name:
            tree.sort_level1_col = None
        if tree.sort_level2_col == col_name:
            tree.sort_level2_col = None
        if tree.sort_level3_col == col_name:
            tree.sort_level3_col = None

        if tree == getattr(self, 'tree', None):
            self.sort_level1_col = tree.sort_level1_col
            self.sort_level2_col = tree.sort_level2_col
            self.sort_level3_col = tree.sort_level3_col
            if not self.sort_level1_col:
                self.multi_sort_click_count = 0

        self.update_mixin_tree_headers(tree)
        self.trigger_mixin_multi_level_sort(tree)
        self._save_mixin_ui_states(tree)

    def clear_all_mixin_multi_sort(self, tree: ttk.Treeview) -> None:
        """清除全部的多级排序"""
        self._init_tree_sort_state(tree)

        tree.sort_level1_col = None
        tree.sort_level1_asc = True
        tree.sort_level2_col = None
        tree.sort_level2_asc = True
        tree.sort_level3_col = None
        tree.sort_level3_asc = True
        tree.sortby_col = None
        tree.sortby_col_ascend = False
        
        if tree == getattr(self, 'tree', None):
            self.sort_level1_col = None
            self.sort_level1_asc = True
            self.sort_level2_col = None
            self.sort_level2_asc = True
            self.sort_level3_col = None
            self.sort_level3_asc = True
            self.sortby_col = None
            self.sortby_col_ascend = False
            self.multi_sort_click_count = 0

        self.update_mixin_tree_headers(tree)
        self.trigger_mixin_multi_level_sort(tree)
            
        self._save_mixin_ui_states(tree)

    def trigger_mixin_multi_level_sort(self, tree: ttk.Treeview, scroll_to_top: bool = False) -> None:
        """通用触发多级排序动作"""
        if hasattr(self, 'trigger_multi_level_sort') and tree == getattr(self, 'tree', None):
            import inspect
            sig = inspect.signature(self.trigger_multi_level_sort)
            if 'scroll_to_top' in sig.parameters:
                self.trigger_multi_level_sort(scroll_to_top=scroll_to_top)
            else:
                self.trigger_multi_level_sort()
            return
        self.perform_tree_multi_level_sort(tree, scroll_to_top=scroll_to_top)

    def perform_tree_multi_level_sort(self, tree: ttk.Treeview, scroll_to_top: bool = False) -> None:
        """直接对 Treeview 中的行进行多级稳定排序"""
        self._init_tree_sort_state(tree)
        
        if hasattr(self, 'trigger_multi_level_sort') and tree == getattr(self, 'tree', None):
            import inspect
            sig = inspect.signature(self.trigger_multi_level_sort)
            if 'scroll_to_top' in sig.parameters:
                self.trigger_multi_level_sort(scroll_to_top=scroll_to_top)
            else:
                self.trigger_multi_level_sort()
            return
            
        bound_cols = set()
        active_levels = []
        
        if tree.sort_level1_col:
            active_levels.append((tree.sort_level1_col, not tree.sort_level1_asc))
            bound_cols.add(tree.sort_level1_col)
        if tree.sort_level2_col:
            active_levels.append((tree.sort_level2_col, not tree.sort_level2_asc))
            bound_cols.add(tree.sort_level2_col)
        if tree.sort_level3_col:
            active_levels.append((tree.sort_level3_col, not tree.sort_level3_asc))
            bound_cols.add(tree.sort_level3_col)
            
        temp_col = tree.sortby_col
        if temp_col and temp_col not in bound_cols and temp_col in tree.cget("columns"):
            active_levels.append((temp_col, not tree.sortby_col_ascend))

        children = tree.get_children('')
        if not children:
            return

        # Determine if we should prioritize favorites (is_fav_key_tree)
        is_fav_key_tree = False
        if children and all(len(str(c)) == 6 and str(c).isdigit() for c in children[:3]):
            is_fav_key_tree = True
        elif hasattr(self, '_member_tree') and tree == getattr(self, '_member_tree', None):
            is_fav_key_tree = True
        elif hasattr(self, '_signal_tree') and tree == getattr(self, '_signal_tree', None):
            is_fav_key_tree = True
        elif hasattr(self, '_guidance_tree') and tree == getattr(self, '_guidance_tree', None):
            is_fav_key_tree = True
            
        if is_fav_key_tree:
            try:
                from global_favorites import GlobalFavoriteManager
                fav_mgr = GlobalFavoriteManager()
                fav_stocks = fav_mgr.get_favorite_stocks()
            except Exception:
                fav_stocks = set()
                
            fav_children = []
            normal_children = []
            for ch in children:
                code = str(ch)
                if code in fav_stocks:
                    fav_children.append(ch)
                else:
                    normal_children.append(ch)
                    
            for col, rev in reversed(active_levels):
                fav_children = self._sort_id_list_by_column_stable(tree, fav_children, col, rev)
                normal_children = self._sort_id_list_by_column_stable(tree, normal_children, col, rev)
                
            if not active_levels:
                # Default stable sort
                fav_children = self._sort_id_list_by_column_stable(tree, fav_children, 'code', False)
                normal_children = self._sort_id_list_by_column_stable(tree, normal_children, 'code', False)
                
            final_children = fav_children + normal_children
        else:
            final_children = list(children)
            for col, rev in reversed(active_levels):
                final_children = self._sort_id_list_by_column_stable(tree, final_children, col, rev)
                
            if not active_levels:
                first_col = tree.cget("columns")[0]
                final_children = self._sort_id_list_by_column_stable(tree, final_children, first_col, False)
                
        for index, ch in enumerate(final_children):
            tree.move(ch, '', index)
            
        if scroll_to_top:
            tree.yview_moveto(0)

    def _sort_id_list_by_column_stable(self, tree: ttk.Treeview, id_list: list, col: str, reverse: bool) -> list:
        """根据某一列的值对 IID 列表进行稳定排序"""
        if col not in tree.cget("columns"):
            return id_list
            
        l = [(tree.set(k, col), k) for k in id_list]
        
        action_priority = {
            "买入建仓": 1, "建仓": 1, "做T回补": 2, "回补": 2,
            "分批大止盈": 3, "大止盈": 3, "止损": 4, "保持观察": 5, "观察": 5
        }
        branch_priority = {
            "5日线主升浪": 1, "5日线极速支撑": 1, "10日线反转": 2, "10日线趋势": 2,
            "SWS盈利线低吸": 3, "SWS防守支撑": 3, "60日线生死防守": 4, "破位高位防震": 5
        }
        
        current_filter = ""
        if hasattr(self, 'concept_filter_var'):
            current_filter = self.concept_filter_var.get().lower().strip()
        elif hasattr(self, 'search_var'):
            current_filter = self.search_var.get().lower().strip()
        elif hasattr(self, 'parent_win') and hasattr(self.parent_win, 'concept_filter_var'):
            current_filter = self.parent_win.concept_filter_var.get().lower().strip()
        kws = current_filter.split() if current_filter else []
        
        def _key_func(t):
            s = str(t[0]).strip()
            if not s or s == '-':
                return (1, "") if not reverse else (-1, "")
                
            if col in ("action", "action_cn"):
                return (0, action_priority.get(s, 99))
            if col in ("branch", "branch_cn"):
                return (0, branch_priority.get(s, 99))
            if col in ("sector", "category") and kws:
                import re
                cats = [c.strip() for c in re.split(r'[;|★\s]', s.lower()) if c.strip() and c.strip() not in ('nan', 'NaN', '0')]
                match_idx = 999
                for idx, cat in enumerate(cats):
                    if any(kw in cat for kw in kws):
                        match_idx = idx
                        break
                prio = match_idx if not reverse else (999 - match_idx)
                return (prio, s)
                
            try:
                cleaned = s.replace('%', '').replace('+', '').replace('★', '').replace('▲', '').replace('▼', '').strip()
                val = float(cleaned)
                return (0, val)
            except (ValueError, TypeError):
                return (2, s.lower())
                
        fm = getattr(self, 'feature_marker', None) or getattr(getattr(self, 'parent_win', None), 'feature_marker', None)
        if col == 'name' and fm:
            l.sort(key=lambda t: (fm.get_priority_score(t[0]), t[0]), reverse=reverse)
        elif col == 'MainU':
            try:
                from mainu_sort import mainu_sort_score
                l.sort(key=lambda t: mainu_sort_score(t[0]), reverse=reverse)
            except Exception:
                l.sort(key=_key_func, reverse=reverse)
        else:
            l.sort(key=_key_func, reverse=reverse)
            
        return [k for _, k in l]

    def show_header_context_menu(self, tree: ttk.Treeview, event: tk.Event) -> bool:
        """通用表头右键多级排序上下文菜单。返回 True 表示事件已被处理，False 表示由行右键菜单继续处理"""
        region = tree.identify_region(event.x, event.y)
        if region != "heading":
            return False
            
        col_id = tree.identify_column(event.x)
        if not col_id:
            return True
            
        col_name = tree.column(col_id, option="id")
        self._init_tree_sort_state(tree)
        
        menu = tk.Menu(tree, tearoff=0)
        menu.add_command(label=f"🔴 设为 【主排序】 ({col_name})", command=lambda: self.set_mixin_multi_sort_level(tree, col_name, 1))
        menu.add_command(label=f"🟡 设为 【从排序】 ({col_name})", command=lambda: self.set_mixin_multi_sort_level(tree, col_name, 2))
        menu.add_command(label=f"🟢 设为 【次排序】 ({col_name})", command=lambda: self.set_mixin_multi_sort_level(tree, col_name, 3))
        menu.add_separator()
        menu.add_command(label=f"❌ 取消此列的排序设置", command=lambda: self.clear_mixin_multi_sort_level(tree, col_name))
        menu.add_command(label=f"🚫 清空所有多级排序", command=lambda: self.clear_all_mixin_multi_sort(tree))
        
        menu.post(event.x_root, event.y_root)
        return True
