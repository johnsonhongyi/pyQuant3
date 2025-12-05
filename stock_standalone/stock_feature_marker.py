# -*- coding: utf-8 -*-
"""
股票特征标记模块
提供行颜色高亮、图标标记等功能
"""

import logging

logger = logging.getLogger(__name__)


class StockFeatureMarker:
    """
    股票特征标记器
    
    功能:
    1. 根据股票特征自动标记颜色
    2. 添加图标标记
    3. 支持自定义标记规则
    """
    
    # 颜色配置
    COLORS = {
        # 涨停/跌停
        'limit_up': {'bg': '#ffcccc', 'fg': '#cc0000'},      # 浅红背景,深红文字
        'limit_down': {'bg': '#ccffcc', 'fg': '#006600'},    # 浅绿背景,深绿文字
        'near_limit_up': {'bg': '#ffe6e6', 'fg': '#ff0000'}, # 接近涨停
        'near_limit_down': {'bg': '#e6ffe6', 'fg': '#00cc00'}, # 接近跌停
        
        # 成交量
        'high_volume': {'bg': '#fff0cc', 'fg': '#ff6600'},   # 橙色
        'ultra_high_volume': {'bg': '#ffcc99', 'fg': '#ff3300'}, # 深橙色
        
        # 概念热点
        'hot_concept': {'bg': '#ffe6f0', 'fg': '#ff0066'},   # 粉色
        
        # 特殊标记
        'starred': {'bg': '#ffffcc', 'fg': '#666600'},       # 黄色(收藏)
        'alert': {'bg': '#ffdddd', 'fg': '#990000'},         # 红色(报警)
    }
    
    # 图标配置
    ICONS = {
        'limit_up': '🔴',
        'limit_down': '🟢',
        'high_volume': '📊',
        'hot_concept': '🔥',
        'new_high': '⬆️',
        'new_low': '⬇️',
        'starred': '⭐',
        'alert': '⚠️',
    }
    
    def __init__(self, tree, enable_colors=True):
        """
        初始化标记器
        
        Args:
            tree: ttk.Treeview实例
            enable_colors: 是否启用颜色显示(默认True)
        """
        self.tree = tree
        self.enable_colors = enable_colors
        self._configure_tags()
    
    def _configure_tags(self):
        """配置Treeview标签颜色"""
        for tag_name, colors in self.COLORS.items():
            self.tree.tag_configure(
                tag_name,
                background=colors.get('bg', ''),
                foreground=colors.get('fg', '')
            )
        
        logger.info(f"✅ 已配置{len(self.COLORS)}种标记颜色")
    
    def set_enable_colors(self, enable: bool):
        """设置是否启用颜色显示"""
        self.enable_colors = enable
    
    def get_tags_for_row(self, row_data: dict) -> list:
        """
        根据行数据获取应用的标签
        
        Args:
            row_data: 行数据字典,包含percent, volume等字段
            
        Returns:
            标签列表
        """
        tags = []
        
        # 获取数据
        percent = row_data.get('percent', 0)
        volume = row_data.get('volume', 0)
        
        # 1. 涨跌停判断
        if percent >= 9.9:
            tags.append('limit_up')
        elif percent >= 8.0:
            tags.append('near_limit_up')
        elif percent <= -9.9:
            tags.append('limit_down')
        elif percent <= -8.0:
            tags.append('near_limit_down')
        
        # 2. 成交量判断
        if volume >= 5.0:
            tags.append('ultra_high_volume')
        elif volume >= 2.0:
            tags.append('high_volume')
        
        # 3. 概念热点判断(如果有category字段)
        category = row_data.get('category', '')
        if category and self._is_hot_concept(category):
            tags.append('hot_concept')
        
        return tags
    
    def _is_hot_concept(self, category: str) -> bool:
        """
        判断是否为热门概念
        
        Args:
            category: 概念字符串
            
        Returns:
            是否为热门概念
        """
        # 热门概念关键词
        hot_keywords = ['AI', '芯片', '新能源', '军工', '半导体', '锂电池']
        
        for keyword in hot_keywords:
            if keyword in category:
                return True
        return False
    
    def get_icon_for_row(self, row_data: dict) -> str:
        """
        根据行数据获取图标
        
        Args:
            row_data: 行数据字典
            
        Returns:
            图标字符串
        """
        icons = []
        
        percent = row_data.get('percent', 0)
        volume = row_data.get('volume', 0)
        
        # 涨跌停图标
        if percent >= 9.9:
            icons.append(self.ICONS['limit_up'])
        elif percent <= -9.9:
            icons.append(self.ICONS['limit_down'])
        
        # 成交量图标
        if volume >= 5.0:
            icons.append(self.ICONS['high_volume'])
        
        # 概念热点图标
        category = row_data.get('category', '')
        if category and self._is_hot_concept(category):
            icons.append(self.ICONS['hot_concept'])
        
        return ' '.join(icons)
    
    def apply_marks(self, item_id: str, row_data: dict, add_icon: bool = False):
        """
        应用标记到指定行
        
        Args:
            item_id: Treeview item ID
            row_data: 行数据字典
            add_icon: 是否添加图标到name列(已废弃,使用独立icon列)
        """
        # ✅ 只在启用颜色时应用标签
        if self.enable_colors:
            tags = self.get_tags_for_row(row_data)
            if tags:
                self.tree.item(item_id, tags=tuple(tags))
        else:
            # 清除标签
            self.tree.item(item_id, tags=())


# 使用示例:
"""
# 1. 在StockMonitorApp.__init__中初始化
self.feature_marker = StockFeatureMarker(self.tree)

# 2. 在refresh_tree中应用标记
def refresh_tree_with_marks(self, df=None):
    # ... 现有的刷新逻辑 ...
    
    # 插入数据时应用标记
    for idx, row in df.iterrows():
        values = [row.get(col, "") for col in cols_to_show]
        iid = self.tree.insert("", "end", values=values)
        
        # 应用特征标记
        row_data = {
            'percent': row.get('percent', 0),
            'volume': row.get('volume', 0),
            'category': row.get('category', '')
        }
        self.feature_marker.apply_marks(iid, row_data, add_icon=False)

# 3. 或者在增量更新时应用
def update_with_marks(self, df):
    added, updated, deleted = self.tree_updater.update(df)
    
    # 为所有可见行应用标记
    for iid in self.tree.get_children():
        values = self.tree.item(iid, 'values')
        if values:
            row_data = {
                'percent': float(values[2]) if len(values) > 2 else 0,
                'volume': float(values[3]) if len(values) > 3 else 0,
            }
            self.feature_marker.apply_marks(iid, row_data)
"""
