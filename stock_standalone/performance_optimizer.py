# -*- coding: utf-8 -*-
"""
股票监控系统性能优化模块
提供Treeview增量更新、数据缓存等性能优化功能
"""

import time
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger()

class TreeviewIncrementalUpdater:
    """
    Treeview增量更新器
    
    核心功能:
    1. 维护行ID到code的映射
    2. 检测数据变化并只更新变化的行
    3. 支持新增、删除、修改行
    4. 大幅减少UI操作,提升流畅度
    """
    
    def __init__(self, tree, columns: List[str], feature_marker=None):
        """
        初始化增量更新器
        
        Args:
            tree: ttk.Treeview实例
            columns: 显示的列名列表
            feature_marker: StockFeatureMarker实例(可选)
        """
        self.tree = tree
        self.columns = columns
        self.feature_marker = feature_marker
        self._item_map: Dict[str, str] = {}  # code -> item_id映射
        self._last_df_hash: Optional[str] = None
        self._update_count = 0
        self._full_refresh_interval = 50  # 每50次增量更新后做一次全量刷新
        
    def update(self, df: pd.DataFrame, force_full: bool = False) -> Tuple[int, int, int]:
        """
        增量更新Treeview
        
        Args:
            df: 新的DataFrame数据
            force_full: 是否强制全量刷新
            
        Returns:
            (新增行数, 更新行数, 删除行数)
        """
        if df is None or df.empty:
            self._clear_all()
            return (0, 0, len(self._item_map))
        
        # 确保code列存在
        if 'code' not in df.columns:
            df = df.copy()
            df.insert(0, 'code', df.index.astype(str))
        
        # 每N次增量更新后强制全量刷新,防止累积误差
        self._update_count += 1
        if self._update_count >= self._full_refresh_interval:
            force_full = True
            self._update_count = 0
            logger.info(f"[TreeviewUpdater] 达到{self._full_refresh_interval}次增量更新,执行全量刷新")
        
        if force_full or not self._item_map:
            return self._full_refresh(df)
        else:
            return self._incremental_update(df)
    
    def _full_refresh(self, df: pd.DataFrame) -> Tuple[int, int, int]:
        """全量刷新"""
        start_time = time.time()
        
        # 清空现有数据
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._item_map.clear()
        
        # 插入所有行
        added = 0
        for idx, row in df.iterrows():
            code = str(row.get('code', idx))
            values = [row.get(col, "") for col in self.columns]
            
            # ✅ 应用特征标记 - 添加图标
            if self.feature_marker:
                try:
                    row_data = {
                        'percent': row.get('percent', 0),
                        'volume': row.get('volume', 0),
                        'category': row.get('category', '')
                    }
                    icon = self.feature_marker.get_icon_for_row(row_data)
                    if icon and 'name' in self.columns:
                        name_idx = self.columns.index('name')
                        if name_idx < len(values):
                            values[name_idx] = f"{icon} {values[name_idx]}"
                except Exception:
                    pass
            
            iid = self.tree.insert("", "end", values=values)
            self._item_map[code] = iid
            
            # ✅ 应用颜色标记（只在启用颜色时）
            if self.feature_marker and self.feature_marker.enable_colors:
                try:
                    row_data = {
                        'percent': row.get('percent', 0),
                        'volume': row.get('volume', 0),
                        'category': row.get('category', '')
                    }
                    tags = self.feature_marker.get_tags_for_row(row_data)
                    if tags:
                        self.tree.item(iid, tags=tuple(tags))
                except Exception:
                    pass
            
            added += 1
        
        duration = time.time() - start_time
        logger.info(f"[TreeviewUpdater] 全量刷新: {added}行, 耗时{duration:.3f}s")
        return (added, 0, 0)
    
    def _incremental_update(self, df: pd.DataFrame) -> Tuple[int, int, int]:
        """增量更新"""
        start_time = time.time()
        
        # 构建新数据的code集合
        new_codes = set(df['code'].astype(str))
        old_codes = set(self._item_map.keys())
        
        # 1. 删除不存在的行
        deleted = 0
        codes_to_delete = old_codes - new_codes
        for code in codes_to_delete:
            if code in self._item_map:
                self.tree.delete(self._item_map[code])
                del self._item_map[code]
                deleted += 1
        
        # 2. 更新现有行 + 新增行
        updated = 0
        added = 0
        
        for idx, row in df.iterrows():
            code = str(row.get('code', idx))
            values = [row.get(col, "") for col in self.columns]
            
            # ✅ 应用特征标记 - 添加图标
            if self.feature_marker:
                try:
                    row_data = {
                        'percent': row.get('percent', 0),
                        'volume': row.get('volume', 0),
                        'category': row.get('category', '')
                    }
                    icon = self.feature_marker.get_icon_for_row(row_data)
                    if icon and 'name' in self.columns:
                        name_idx = self.columns.index('name')
                        if name_idx < len(values):
                            values[name_idx] = f"{icon} {values[name_idx]}"
                except Exception:
                    pass
            
            if code in self._item_map:
                # 更新现有行
                iid = self._item_map[code]
                old_values = self.tree.item(iid, "values")
                
                # 只有值变化时才更新
                if tuple(values) != tuple(old_values):
                    self.tree.item(iid, values=values)
                    updated += 1
                    
                    # ✅ 更新颜色标记（只在启用颜色时）
                    if self.feature_marker and self.feature_marker.enable_colors:
                        try:
                            row_data = {
                                'percent': row.get('percent', 0),
                                'volume': row.get('volume', 0),
                                'category': row.get('category', '')
                            }
                            tags = self.feature_marker.get_tags_for_row(row_data)
                            if tags:
                                self.tree.item(iid, tags=tuple(tags))
                        except Exception:
                            pass
                    elif self.feature_marker and not self.feature_marker.enable_colors:
                        # 关闭颜色时清除标签
                        self.tree.item(iid, tags=())
            else:
                # 新增行
                iid = self.tree.insert("", "end", values=values)
                self._item_map[code] = iid
                added += 1
                
                # ✅ 应用颜色标记（只在启用颜色时）
                if self.feature_marker and self.feature_marker.enable_colors:
                    try:
                        row_data = {
                            'percent': row.get('percent', 0),
                            'volume': row.get('volume', 0),
                            'category': row.get('category', '')
                        }
                        tags = self.feature_marker.get_tags_for_row(row_data)
                        if tags:
                            self.tree.item(iid, tags=tuple(tags))
                    except Exception:
                        pass
        
        duration = time.time() - start_time
        logger.info(f"[TreeviewUpdater] 增量更新: +{added} ~{updated} -{deleted}行, 耗时{duration:.3f}s")
        return (added, updated, deleted)
    
    def _clear_all(self):
        """清空所有数据"""
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._item_map.clear()
    
    def restore_selection(self, code: str) -> bool:
        """
        恢复选中状态
        
        Args:
            code: 要选中的股票代码
            
        Returns:
            是否成功恢复选中
        """
        if code and code in self._item_map:
            iid = self._item_map[code]
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            return True
        return False


class DataFrameCache:
    """
    DataFrame数据缓存器
    
    功能:
    1. 基于TTL的缓存机制
    2. 支持哈希校验,避免重复计算
    3. 自动过期清理
    """
    
    def __init__(self, ttl: int = 5):
        """
        初始化缓存器
        
        Args:
            ttl: 缓存有效期(秒)
        """
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self._ttl = ttl
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        if key in self._cache:
            if time.time() - self._timestamps[key] < self._ttl:
                return self._cache[key]
            else:
                # 过期,删除
                del self._cache[key]
                del self._timestamps[key]
        return None
    
    def set(self, key: str, value: Any):
        """设置缓存数据"""
        self._cache[key] = value
        self._timestamps[key] = time.time()
    
    def clear(self):
        """清空所有缓存"""
        self._cache.clear()
        self._timestamps.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        now = time.time()
        valid_count = sum(1 for ts in self._timestamps.values() if now - ts < self._ttl)
        return {
            "total": len(self._cache),
            "valid": valid_count,
            "expired": len(self._cache) - valid_count
        }


class PerformanceMonitor:
    """
    性能监控器
    
    功能:
    1. 记录函数执行时间
    2. 统计平均/最大/最小耗时
    3. 生成性能报告
    """
    
    def __init__(self, name: str = "Performance"):
        self.name = name
        self._records: List[float] = []
        self._max_records = 100  # 最多保留100条记录
    
    def record(self, duration: float):
        """记录一次执行时间"""
        self._records.append(duration)
        if len(self._records) > self._max_records:
            self._records.pop(0)
    
    def get_stats(self) -> Dict[str, float]:
        """获取统计信息"""
        if not self._records:
            return {"count": 0}
        
        return {
            "count": len(self._records),
            "avg": sum(self._records) / len(self._records),
            "min": min(self._records),
            "max": max(self._records),
            "last": self._records[-1]
        }
    
    def report(self) -> str:
        """生成性能报告"""
        stats = self.get_stats()
        if stats["count"] == 0:
            return f"[{self.name}] 无数据"
        
        return (f"[{self.name}] "
                f"次数:{stats['count']} "
                f"平均:{stats['avg']:.3f}s "
                f"最小:{stats['min']:.3f}s "
                f"最大:{stats['max']:.3f}s "
                f"最近:{stats['last']:.3f}s")


def optimize_dataframe_operations(df: pd.DataFrame, ratio_t: float) -> pd.DataFrame:
    """
    优化DataFrame操作,使用向量化替代map()
    
    Args:
        df: 原始DataFrame
        ratio_t: 时间比例系数
        
    Returns:
        优化后的DataFrame
    """
    df = df.copy()
    
    # 优化前: 使用map()
    # df['volume'] = list(
    #     map(lambda x, y: round(x / y / ratio_t, 1),
    #         df['volume'].values,
    #         df.last6vol.values)
    # )
    
    # 优化后: 使用向量化操作
    if 'volume' in df.columns and 'last6vol' in df.columns:
        df['volume'] = (df['volume'] / df['last6vol'] / ratio_t).round(1)
    
    return df


# 使用示例:
"""
# 1. 在StockMonitorApp.__init__中初始化
self.tree_updater = TreeviewIncrementalUpdater(self.tree, self.current_cols)
self.df_cache = DataFrameCache(ttl=5)
self.perf_monitor = PerformanceMonitor("TreeUpdate")

# 2. 在refresh_tree中使用增量更新
def refresh_tree_optimized(self, df=None):
    start_time = time.time()
    
    if df is None:
        df = self.current_df.copy()
    
    # 使用增量更新
    added, updated, deleted = self.tree_updater.update(df)
    
    # 恢复选中
    if self.select_code:
        self.tree_updater.restore_selection(self.select_code)
    
    # 保存数据
    self.current_df = df
    
    # 更新状态
    self.update_status()
    
    # 记录性能
    duration = time.time() - start_time
    self.perf_monitor.record(duration)
    
    # 每10次更新打印一次性能报告
    if self.perf_monitor.get_stats()["count"] % 10 == 0:
        logger.info(self.perf_monitor.report())

# 3. 在update_tree中使用缓存
def update_tree_optimized(self):
    if not hasattr(self, "tree") or not self.tree.winfo_exists():
        return
    
    try:
        if self.refresh_enabled:
            while not self.queue.empty():
                df = self.queue.get_nowait()
                
                # 检查缓存
                df_hash = pd.util.hash_pandas_object(df).sum()
                cached_df = self.df_cache.get(f"processed_{df_hash}")
                
                if cached_df is not None:
                    logger.info("[Cache] 使用缓存数据")
                    df = cached_df
                else:
                    # 处理数据
                    if self.sortby_col is not None:
                        df = df.sort_values(by=self.sortby_col, ascending=self.sortby_col_ascend)
                    
                    if len(df) > 30:
                        df = detect_signals(df)
                    
                    # 缓存处理后的数据
                    self.df_cache.set(f"processed_{df_hash}", df)
                
                self.df_all = df.copy()
                
                # 使用优化的刷新函数
                if self.search_var1.get() or self.search_var2.get():
                    self.apply_search()
                else:
                    self.refresh_tree_optimized(self.df_all)
                
                self.status_var2.set(f'queue update: {self.format_next_time()}')
    
    except Exception as e:
        logger.error(f"Error updating tree: {e}", exc_info=True)
    finally:
        self.after(1000, self.update_tree_optimized)
"""
