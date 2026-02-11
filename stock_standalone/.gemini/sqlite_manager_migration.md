# 统一使用 SQLiteConnectionManager 修复方案

## 目标
将 `trading_hub.py` 中所有的 `sqlite3.connect()` 替换为 `SQLiteConnectionManager`

## 需要修改的位置

### 1. 导入部分
**位置**: 第 18 行
**修改前**:
```python
import sqlite3
```

**修改后**:
```python
import sqlite3
from db_utils import SQLiteConnectionManager
```

### 2. 所有数据库连接
需要将所有的:
```python
conn = sqlite3.connect(self.signal_db)
c = conn.cursor()
```

替换为:
```python
mgr = SQLiteConnectionManager.get_instance(self.signal_db)
conn = mgr.get_connection()
c = conn.cursor()
```

## 涉及的函数列表
1. `_init_tables()` - 第 101 行
2. `add_to_follow_queue()` - 第 253 行
3. `delete_from_follow_queue()` - 第 303 行
4. `get_follow_queue()` - 第 320 行
5. `update_follow_status()` - 第 389 行
6. `get_follow_queue_df()` - 第 451 行
7. `get_watchlist_df()` - 第 503 行
8. `cleanup_stale_signals()` - 第 566 行
9. `check_db_integrity()` - 第 703 行
10. `add_position()` - 第 716 行
11. `get_positions()` - 第 741 行
12. `update_position_price()` - 第 781 行
13. 以及其他所有使用 `sqlite3.connect()` 的地方

## 注意事项
1. `SQLiteConnectionManager` 使用线程本地连接,避免锁问题
2. 连接关闭仍然使用 `conn.close()`,但实际上连接会被复用
3. 保持原有的事务逻辑(`conn.commit()`)
