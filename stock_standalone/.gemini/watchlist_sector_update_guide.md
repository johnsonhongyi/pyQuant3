# Watch 标签页板块信息更新说明

## 问题说明

Watch 标签页中的板块信息可能为空,需要批量更新。

## 解决方案

已在 `trading_hub.py` 中添加了 `batch_update_watchlist_sectors()` 函数,可以批量更新板块信息。

## 使用方法

### 方法 1: 在代码中调用

在合适的位置(如主窗口初始化后)调用:

```python
from trading_hub import get_trading_hub

# 获取 TradingHub 实例
hub = get_trading_hub()

# 批量更新板块信息 (需要传入 df_all)
if hasattr(main_window, 'df_all') and main_window.df_all is not None:
    updated_count = hub.batch_update_watchlist_sectors(main_window.df_all)
    print(f"已更新 {updated_count} 条记录的板块信息")
```

### 方法 2: 在 HotlistPanel 中自动更新

可以在 `hotlist_panel.py` 的 `_refresh_pnl()` 函数中添加定期更新逻辑:

```python
def _refresh_pnl(self):
    # ... 现有代码 ...
    
    # [NEW] 定期更新板块信息 (每5分钟一次)
    if not hasattr(self, '_last_sector_update_time'):
        self._last_sector_update_time = 0
    
    now = time.time()
    if now - self._last_sector_update_time > 300:  # 5分钟
        try:
            hub = get_trading_hub()
            if hasattr(main_window, 'df_all') and main_window.df_all is not None:
                updated_count = hub.batch_update_watchlist_sectors(main_window.df_all)
                if updated_count > 0:
                    logger.info(f"[Watchlist] Updated {updated_count} sectors")
                    # 触发 Watchlist 刷新
                    self._update_watchlist_queue()
            self._last_sector_update_time = now
        except Exception as e:
            logger.error(f"Update watchlist sectors error: {e}")
```

### 方法 3: 手动执行脚本

创建一个独立脚本 `update_watchlist_sectors.py`:

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量更新 Watchlist 板块信息
"""

import sys
sys.path.insert(0, '.')

from trading_hub import get_trading_hub
import pandas as pd

def main():
    # 1. 获取 TradingHub
    hub = get_trading_hub()
    
    # 2. 获取 df_all (需要从主程序获取)
    # 这里假设你有办法获取 df_all,例如:
    # - 从文件加载
    # - 从数据库查询
    # - 从 API 获取
    
    # 示例: 从 pickle 文件加载 (如果有缓存)
    try:
        df_all = pd.read_pickle('df_all_cache.pkl')
    except:
        print("无法加载 df_all,请确保数据可用")
        return
    
    # 3. 批量更新
    updated_count = hub.batch_update_watchlist_sectors(df_all)
    print(f"✅ 已更新 {updated_count} 条记录的板块信息")

if __name__ == '__main__':
    main()
```

## 函数说明

### `batch_update_watchlist_sectors(df_all: pd.DataFrame) -> int`

**功能**: 批量更新 watchlist 中的板块信息

**参数**:
- `df_all`: 主数据框,必须包含 `category` 字段

**返回值**:
- 更新的记录数

**逻辑**:
1. 查询所有板块信息为空的记录
2. 从 `df_all` 中获取对应股票的 `category` 字段
3. 取第一个板块作为主板块
4. 批量更新到数据库

**示例**:
```python
hub = get_trading_hub()
count = hub.batch_update_watchlist_sectors(main_window.df_all)
print(f"Updated {count} records")
```

## 数据流说明

```
df_all (主数据框)
    ↓
category 字段 (多个板块,用 ; 分隔)
    ↓
取第一个板块
    ↓
hot_stock_watchlist.sector (数据库)
    ↓
Watchlist UI (显示)
```

## 注意事项

1. **数据源**: 确保 `df_all` 包含 `category` 字段
2. **板块选择**: 如果一只股票属于多个板块,只会取第一个
3. **更新频率**: 建议每 5-10 分钟更新一次,避免频繁操作
4. **性能**: 批量更新操作已优化,只更新板块为空的记录

## 验证方法

更新后,在 Watch 标签页中应该能看到板块信息:

```
序号 | 状态 | 代码 | 名称 | 板块 | 发现价 | 现价 | 盈亏%
-----|------|------|------|------|--------|------|------
1    | WATCHING | 601869 | 长飞光纤 | 光通信 | 28.00 | 29.50 | +5.36%
```

如果板块列仍然为空,检查:
1. `df_all` 中是否有对应股票的数据
2. `category` 字段是否有值
3. 数据库连接是否正常

---

**更新完成** ✅
