# -*- coding: utf-8 -*-
"""
股票特征标记模块
提供行颜色高亮、图标标记等功能
"""
# import logging
# logger = logging.getLogger(__name__)
from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger()
import pandas as pd


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
        'bullish_trend': {'bg': '#FFF0F5', 'fg': '#800080'}, # [NEW] 淡紫/深红趋势高亮
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
        'bullish_trend': '🚀',   # [NEW] 强势波段标识
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
        # [NEW] 🚀 确保强势趋势样式在所有列表(主表/Top10)中均全局生效
        self.tree.tag_configure("bullish_trend", background="#FFF0F5", font=("Arial", 10, "bold"))
        
        logger.info(f"✅ 已配置{len(self.COLORS)}种标记颜色")
    
    def set_enable_colors(self, enable: bool):
        """设置是否启用颜色显示"""
        self.enable_colors = enable
    
    def get_tags_for_row(self, row_data: dict) -> list:
        """
        根据行数据获取应用的标签
        
        Args:
            row_data: 行数据字典,包含多个技术指标
            
        Returns:
            标签列表
        """
        tags = []
        
        # 获取所有关键指标
        percent = row_data.get('percent', 0)
        volume = row_data.get('volume', 0)
        # price = row_data.get('price', 0)
        # high4 = row_data.get('high4', 0)
        # max5 = row_data.get('max5', 0)
        # hmax = row_data.get('hmax', 0)
        # low4 = row_data.get('low4', 0)
        # lastdu4 = row_data.get('lastdu4', 0)
        
        # 1. 涨跌停与强势判断 (用户定制逻辑)
        if percent >= 6 and volume > 2:
            tags.append('limit_up')
        elif percent >= 4.0:
            tags.append('near_limit_up')
        elif percent <= -9.9:
            tags.append('limit_down')
        elif percent <= -7.0:
            tags.append('near_limit_down')
        
        # 2. 成交量判断
        if volume >= 5.0:
            tags.append('ultra_high_volume')
        elif volume >= 2.0:
            tags.append('high_volume')
        
        # 3. 概念热点判断(如果有category字段)
        # 4. [NEW] 趋势排列判断
        ma5 = row_data.get('ma5d')
        ma20 = row_data.get('ma20d')
        ma60 = row_data.get('ma60d')
        if ma5 and ma20 and ma60:
            if ma5 > ma20 > ma60 and row_data.get('price', 0) > ma60:
                tags.append('bullish_trend')
                
        return tags
    
    def _is_hot_concept(self, category: str) -> bool:
        """
        判断是否为热门概念
        """
        hot_keywords = ['AI', '芯片', '新能源', '军工', '半导体', '锂电池', '固态电池', '机器人']
        for keyword in hot_keywords:
            if keyword in category:
                return True
        return False
    
    def get_icon_for_row(self, row_data: dict) -> str:
        """
        根据详细技术指标获取复合图标
        """
        icons = []
        
        # 提取数据点
        percent = row_data.get('percent', 0)
        percent = 0 if percent == -100 else percent
        volume = row_data.get('volume', 0)
        price = row_data.get('price', 0)
        max5 = row_data.get('max5', 0)
        hmax = row_data.get('hmax', 0)
        min5 = row_data.get('min5', 0)
        lmin = row_data.get('lmin', 0)
        lastdu4 = row_data.get('lastdu4', 0)
        low4 = row_data.get('low4', 0)
        category = row_data.get('category', '')

        # 1. 强势/涨停图标 (🔴)
        if percent >= 6 and volume > 2:
            icons.append(self.ICONS['limit_up'])
        
        # 2. 弱势/跌停图标 (🟢)
        if percent <= -9.9 and percent > -31:
            icons.append(self.ICONS['limit_down'])
        
        # 3. 成交量异常 (📊)
        if volume >= 2.0:
            icons.append(self.ICONS['high_volume'])
        
        # 4. 概念热点 (🔥)
        if category and self._is_hot_concept(category):
            icons.append(self.ICONS['hot_concept'])
        
        # 5. 突破新高 (⬆️)
        if price > 0:
            if (hmax > 0 and price >= hmax) or (max5 > 0 and price >= max5):
                icons.append(self.ICONS['new_high'])

        # 6. 跌破新低 (⬇️)
        if price > 0:
            if (lmin > 0 and price <= lmin) or (min5 > 0 and price <= min5):
                icons.append(self.ICONS['new_low'])

        # 7. 连阳/星标 (⭐)
        if lastdu4 >= 3:
            icons.append(self.ICONS['starred'])

        # 9. [NEW] 🚀 均线趋势识别 (MA5 > MA20 > MA60)
        ma5 = row_data.get('ma5d')
        ma20 = row_data.get('ma20d')
        ma60 = row_data.get('ma60d')
        if ma5 and ma20 and ma60:
            if ma5 > ma20 > ma60 and price > ma60:
                # 注入火箭图标，并确保排在较前位置（优先级高）
                icons.insert(0, self.ICONS['bullish_trend'])
            
        return ''.join(icons)
    
    def process_dataframe(self, df: pd.DataFrame) -> dict:
        """
        批量处理DataFrame，返回 {code: (tags, icon)} 映射
        
        Args:
            df: 包含技术指标的DataFrame
            
        Returns:
            dict: {code: (tags, icon)}
        """
        results = {}
        if df.empty:
            return results
            
        # 确保 code 列存在
        if 'code' not in df.columns:
            # 尝试从 index 获取
            df = df.copy()
            df['code'] = df.index
            
        # 预取所有可能需要的列，如果缺失则填充默认值，避免循环中频繁判断
        cols_needed = [
            'percent', 'volume', 'price', 'trade', 'high4', 'max5', 'max10', 
            'hmax', 'hmax60', 'low4', 'low10', 'low60', 'lmin', 'min5', 
            'cmean', 'hv', 'lv', 'llowvol', 'lastdu4', 'category',
            'ma5d', 'ma20d', 'ma60d'
        ]
        
        df_proc = df.copy()
        for col in cols_needed:
            if col not in df_proc.columns:
                # 特殊映射: price 可能叫 trade
                if col == 'price' and 'trade' in df_proc.columns:
                    df_proc['price'] = df_proc['trade']
                else:
                    df_proc[col] = 0 if col != 'category' else ''
        
        # 转换为字典列表处理更高效
        items = df_proc.to_dict('records')
        for item in items:
            code = str(item.get('code', ''))
            if not code: continue
            
            tags = self.get_tags_for_row(item) if self.enable_colors else []
            icon = self.get_icon_for_row(item)
            results[code] = (tags, icon)
            
        return results
    
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
            # 清除标签（关闭颜色时）
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
