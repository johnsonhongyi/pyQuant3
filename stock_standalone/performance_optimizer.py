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
    5. 批量插入优化: 隐藏displaycolumns减少重绘
    6. 分块插入优化: 大量数据分批异步插入避免UI阻塞
    """
    
    def __init__(self, tree, columns: List[str], feature_marker=None, 
                 root=None, chunk_size: int = 200, chunk_threshold: int = 500):
        """
        初始化增量更新器
        
        Args:
            tree: ttk.Treeview实例
            columns: 显示的列名列表
            feature_marker: StockFeatureMarker实例(可选)
            root: Tk根窗口(用于分块插入的after调度)
            chunk_size: 每批插入的行数(默认200)
            chunk_threshold: 启用分块插入的行数阈值(默认500)
        """
        self.tree = tree
        self.columns = columns
        self.feature_marker = feature_marker
        self.root = root  # 用于 after() 调度
        self.chunk_size = chunk_size
        self.chunk_threshold = chunk_threshold
        self._item_map: Dict[str, str] = {}  # code -> item_id映射
        self._last_df_hash: Optional[str] = None
        self._update_count = 0
        self._full_refresh_interval = 50  # 每50次增量更新后做一次全量刷新
        self._chunked_insert_pending = False  # 是否有分块插入正在进行
        self._pending_callback: Optional[callable] = None  # 分块完成后的回调
        
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
    
    def _full_refresh(self, df: pd.DataFrame, callback: Optional[callable] = None) -> Tuple[int, int, int]:
        """
        全量刷新 - 优化版
        
        优化策略:
        1. 隐藏 displaycolumns: 批量插入时隐藏列，完成后恢复，减少重绘开销
        2. 分块插入: 数据量超过阈值时，分批异步插入避免 UI 阻塞
        
        Args:
            df: 数据 DataFrame
            callback: 分块插入完成后的回调函数
        """
        start_time = time.time()
        row_count = len(df)
        
        # 清空现有数据
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._item_map.clear()
        
        # 预处理所有行数据
        rows_data = self._prepare_rows(df)
        
        # 根据数据量决定插入策略
        if row_count > self.chunk_threshold and self.root is not None:
            # 分块异步插入
            logger.info(f"[TreeviewUpdater] 启用分块插入: {row_count}行, 每批{self.chunk_size}行")
            self._chunked_insert_pending = True
            self._pending_callback = callback
            self._chunked_insert(rows_data, 0, start_time)
            return (row_count, 0, 0)  # 异步执行，返回预计插入数
        else:
            # 同步批量插入 + displaycolumns 优化
            added = self._batch_insert_with_displaycolumns_optimization(rows_data)
            duration = time.time() - start_time
            logger.info(f"[TreeviewUpdater] 全量刷新(批量优化): {added}行, 耗时{duration:.3f}s")
            return (added, 0, 0)
    
    def _prepare_rows_fast(self, df: pd.DataFrame) -> list:
        """
        极速预处理 - 最大化性能优化版本
        
        优化策略:
        1. 预提取所有需要的列为独立数组（避免循环内索引）
        2. 使用 numpy tolist() 批量转换
        3. 本地变量缓存减少属性查找
        4. 最小化循环内函数调用
        """
        import time
        import numpy as np
        prep_start = time.time()
        
        n_rows = len(df)
        if n_rows == 0:
            return []
        
        # 本地变量缓存
        columns = self.columns
        feature_marker = self.feature_marker
        
        # 预提取 code 列
        if 'code' in df.columns:
            codes = df['code'].astype(str).tolist()
        else:
            codes = [str(i) for i in df.index]
        
        # 预提取显示列的值（使用 numpy 提取每列，然后组装）
        col_arrays = []
        for col in columns:
            if col in df.columns:
                # fillna 处理 NaN
                arr = df[col].fillna('').tolist()
            else:
                arr = [''] * n_rows
            col_arrays.append(arr)
        
        # 预提取特征标记需要的列（如果启用）
        feature_data = None
        if feature_marker and feature_marker.enable_colors:
            feature_cols = {
                'percent': None, 'volume': None, 'category': None,
                'price': None, 'trade': None,
                'high4': None, 'max5': None, 'max10': None,
                'hmax': None, 'hmax60': None,
                'low4': None, 'low10': None, 'low60': None,
                'lmin': None, 'min5': None, 'cmean': None,
                'hv': None, 'lv': None, 'llowvol': None, 'lastdu4': None
            }
            for k in feature_cols:
                if k in df.columns:
                    # fillna(0) 用于数值，fillna('') 用于字符串
                    if k == 'category':
                        feature_cols[k] = df[k].fillna('').tolist()
                    else:
                        feature_cols[k] = df[k].fillna(0).tolist()
                else:
                    feature_cols[k] = None
            feature_data = feature_cols
        
        # name 列在 columns 中的索引
        name_idx = columns.index('name') if 'name' in columns else -1
        
        # 构建结果（最小化循环内操作）
        rows_data = []
        n_cols = len(columns)
        
        for i in range(n_rows):
            code = codes[i]
            
            # 构建 values 列表（使用预提取的列数组）
            values = [col_arrays[j][i] for j in range(n_cols)]
            
            # 特征标记处理
            row_data = None
            if feature_data:
                try:
                    # 快速构建 row_data 字典
                    fd = feature_data
                    price_val = fd['price'][i] if fd['price'] else 0
                    if price_val == 0 and fd['trade']:
                        price_val = fd['trade'][i]
                    
                    row_data = {
                        'percent': fd['percent'][i] if fd['percent'] else 0,
                        'volume': fd['volume'][i] if fd['volume'] else 0,
                        'category': fd['category'][i] if fd['category'] else '',
                        'price': price_val,
                        'high4': fd['high4'][i] if fd['high4'] else 0,
                        'max5': fd['max5'][i] if fd['max5'] else 0,
                        'max10': fd['max10'][i] if fd['max10'] else 0,
                        'hmax': fd['hmax'][i] if fd['hmax'] else 0,
                        'hmax60': fd['hmax60'][i] if fd['hmax60'] else 0,
                        'low4': fd['low4'][i] if fd['low4'] else 0,
                        'low10': fd['low10'][i] if fd['low10'] else 0,
                        'low60': fd['low60'][i] if fd['low60'] else 0,
                        'lmin': fd['lmin'][i] if fd['lmin'] else 0,
                        'min5': fd['min5'][i] if fd['min5'] else 0,
                        'cmean': fd['cmean'][i] if fd['cmean'] else 0,
                        'hv': fd['hv'][i] if fd['hv'] else 0,
                        'lv': fd['lv'][i] if fd['lv'] else 0,
                        'llowvol': fd['llowvol'][i] if fd['llowvol'] else 0,
                        'lastdu4': fd['lastdu4'][i] if fd['lastdu4'] else 0
                    }
                    
                    # 添加图标
                    if name_idx >= 0:
                        icon = feature_marker.get_icon_for_row(row_data)
                        if icon:
                            values[name_idx] = f"{icon} {values[name_idx]}"
                except Exception:
                    row_data = None
            
            rows_data.append((code, values, row_data))
        
        prep_time = time.time() - prep_start
        if prep_time > 0.1:
            logger.debug(f"[TreeviewUpdater] 数据预处理: {n_rows}行, 耗时{prep_time:.3f}s")
        
        return rows_data
        
    
    def _prepare_rows(self, df: pd.DataFrame) -> list:
        """
        预处理所有行数据 - 使用快速方法
        """
        return self._prepare_rows_fast(df)
    
    def _batch_insert_with_displaycolumns_optimization(
        self, rows_data: List[Tuple[str, list, Optional[dict]]]
    ) -> int:
        """
        使用 displaycolumns 隐藏优化进行批量插入
        
        原理: 隐藏列后插入不会触发每行的重绘，最后恢复列时只重绘一次
        """
        try:
            # 保存当前 displaycolumns 设置
            saved_displaycolumns = self.tree["displaycolumns"]
            
            # 隐藏所有列（设为空元组）
            self.tree["displaycolumns"] = ()
            
            # 批量插入
            added = 0
            for code, values, row_data in rows_data:
                iid = self.tree.insert("", "end", values=values)
                self._item_map[code] = iid
                
                # 应用颜色标记
                if row_data and self.feature_marker and self.feature_marker.enable_colors:
                    try:
                        tags = self.feature_marker.get_tags_for_row(row_data)
                        if tags:
                            self.tree.item(iid, tags=tuple(tags))
                    except Exception:
                        pass
                
                added += 1
            
            # 恢复 displaycolumns（只触发一次重绘）
            self.tree["displaycolumns"] = saved_displaycolumns
            
            return added
            
        except Exception as e:
            logger.warning(f"[TreeviewUpdater] displaycolumns优化失败，回退普通模式: {e}")
            # 回退到普通模式
            return self._batch_insert_plain(rows_data)
    
    def _batch_insert_plain(self, rows_data: List[Tuple[str, list, Optional[dict]]]) -> int:
        """普通批量插入（无优化）"""
        added = 0
        for code, values, row_data in rows_data:
            iid = self.tree.insert("", "end", values=values)
            self._item_map[code] = iid
            
            if row_data and self.feature_marker and self.feature_marker.enable_colors:
                try:
                    tags = self.feature_marker.get_tags_for_row(row_data)
                    if tags:
                        self.tree.item(iid, tags=tuple(tags))
                except Exception:
                    pass
            
            added += 1
        return added
    
    def _chunked_insert(
        self, 
        rows_data: List[Tuple[str, list, Optional[dict]]], 
        start_idx: int,
        start_time: float
    ):
        """
        分块异步插入
        
        使用 root.after() 分批插入数据，避免长时间阻塞 UI 线程
        
        Args:
            rows_data: 预处理的行数据
            start_idx: 当前批次的起始索引
            start_time: 总操作开始时间
        """
        if not self.root:
            # 无法异步，回退同步模式
            self._batch_insert_with_displaycolumns_optimization(rows_data)
            return
        
        end_idx = min(start_idx + self.chunk_size, len(rows_data))
        chunk = rows_data[start_idx:end_idx]
        
        try:
            # 隐藏列进行本批次插入
            saved_displaycolumns = self.tree["displaycolumns"]
            self.tree["displaycolumns"] = ()
            
            for code, values, row_data in chunk:
                iid = self.tree.insert("", "end", values=values)
                self._item_map[code] = iid
                
                if row_data and self.feature_marker and self.feature_marker.enable_colors:
                    try:
                        tags = self.feature_marker.get_tags_for_row(row_data)
                        if tags:
                            self.tree.item(iid, tags=tuple(tags))
                    except Exception:
                        pass
            
            self.tree["displaycolumns"] = saved_displaycolumns
            
        except Exception as e:
            logger.debug(f"Chunked insert chunk failed: {e}")
            # 回退普通插入
            for code, values, row_data in chunk:
                iid = self.tree.insert("", "end", values=values)
                self._item_map[code] = iid
        
        # 检查是否还有更多数据
        if end_idx < len(rows_data):
            # 安排下一批次（1ms 延迟，让 UI 有机会响应）
            self.root.after(1, self._chunked_insert, rows_data, end_idx, start_time)
        else:
            # 插入完成
            self._chunked_insert_pending = False
            duration = time.time() - start_time
            logger.info(f"[TreeviewUpdater] 全量刷新(分块优化): {len(rows_data)}行, 耗时{duration:.3f}s")
            
            # 执行回调
            if self._pending_callback:
                try:
                    self._pending_callback()
                except Exception as e:
                    logger.debug(f"Chunked insert callback failed: {e}")
                self._pending_callback = None
    
    def _incremental_update(self, df: pd.DataFrame) -> Tuple[int, int, int]:
        """
        增量更新 - 优化版
        
        优化策略:
        1. 分离新增行和更新行的处理
        2. 对新增行使用 displaycolumns 隐藏优化批量插入
        3. 更新行仍逐行处理（通常数量较少）
        """
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
        
        # 2. 使用快速方法准备数据（避免 iterrows）
        # 预计算列索引映射
        df_columns = list(df.columns)
        col_indices = {}
        for col in self.columns:
            if col in df_columns:
                col_indices[col] = df_columns.index(col)
            else:
                col_indices[col] = -1
        
        code_idx = df_columns.index('code') if 'code' in df_columns else -1
        data_array = df.values
        n_rows = len(data_array)
        
        rows_to_update: list = []  # (code, values, iid)
        rows_to_add: list = []     # (code, values)
        
        for i in range(n_rows):
            row_arr = data_array[i]
            
            # 获取 code
            if code_idx >= 0:
                code = str(row_arr[code_idx])
            else:
                code = str(df.index[i])
            
            # 构建 values 列表
            values = []
            for col in self.columns:
                idx = col_indices[col]
                if idx >= 0:
                    val = row_arr[idx]
                    if pd.isna(val):
                        values.append("")
                    else:
                        values.append(val)
                else:
                    values.append("")
            
            if code in self._item_map:
                iid = self._item_map[code]
                rows_to_update.append((code, values, iid))
            else:
                rows_to_add.append((code, values, None))
        
        # 3. 批量新增行（使用 displaycolumns 优化）
        added = 0
        if rows_to_add:
            added = self._batch_add_rows(rows_to_add)
        
        # 4. 逐行更新（通常数量少，简化处理）
        updated = 0
        for code, values, iid in rows_to_update:
            try:
                old_values = self.tree.item(iid, "values")
                
                # 只有值变化时才更新
                if tuple(values) != tuple(old_values):
                    self.tree.item(iid, values=values)
                    updated += 1
            except Exception as e:
                logger.debug(f"Update row failed: {e}")
                try:
                    self.tree.item(iid, values=values)
                    updated += 1
                except Exception:
                    pass
        
        duration = time.time() - start_time
        logger.info(f"[TreeviewUpdater] 增量更新: +{added} ~{updated} -{deleted}行, 耗时{duration:.3f}s")
        return (added, updated, deleted)
    
    def _batch_add_rows(self, rows_to_add: List[Tuple[str, list, Optional[dict]]]) -> int:
        """
        批量新增行 - 使用 displaycolumns 优化
        
        Args:
            rows_to_add: (code, values, row_data) 列表
            
        Returns:
            成功添加的行数
        """
        if not rows_to_add:
            return 0
        
        add_count = len(rows_to_add)
        
        try:
            # 保存当前 displaycolumns 设置
            saved_displaycolumns = self.tree["displaycolumns"]
            
            # 隐藏所有列减少重绘
            self.tree["displaycolumns"] = ()
            
            added = 0
            for code, values, row_data in rows_to_add:
                iid = self.tree.insert("", "end", values=values)
                self._item_map[code] = iid
                
                # 应用颜色标记
                if row_data and self.feature_marker and self.feature_marker.enable_colors:
                    try:
                        tags = self.feature_marker.get_tags_for_row(row_data)
                        if tags:
                            self.tree.item(iid, tags=tuple(tags))
                    except Exception:
                        pass
                
                added += 1
            
            # 恢复列显示（只触发一次重绘）
            self.tree["displaycolumns"] = saved_displaycolumns
            
            if add_count > 100:
                logger.debug(f"[TreeviewUpdater] 批量新增优化: {added}行")
            
            return added
            
        except Exception as e:
            logger.warning(f"[TreeviewUpdater] 批量新增优化失败: {e}")
            # 回退普通模式
            added = 0
            for code, values, row_data in rows_to_add:
                try:
                    iid = self.tree.insert("", "end", values=values)
                    self._item_map[code] = iid
                    added += 1
                except Exception:
                    pass
            return added
    
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
        self._total_count = 0    # ⚡ 总调用次数（不会重置）
    
    def record(self, duration: float):
        """记录一次执行时间"""
        self._records.append(duration)
        self._total_count += 1  # ⚡ 累计总次数
        if len(self._records) > self._max_records:
            self._records.pop(0)
    
    def get_stats(self) -> Dict[str, float]:
        """获取统计信息"""
        if not self._records:
            return {"count": 0, "total_count": 0}
        
        return {
            "count": len(self._records),
            "total_count": self._total_count,  # ⚡ 返回总次数
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
                f"次数:{stats['total_count']} "  # ⚡ 显示总次数
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
