# 信号去重修复总结

## 修复时间
2026-02-11 16:51

## 问题描述

### 问题1: `instock` 模块导入错误
**错误信息**: 
```
[02-11 16:28:24] ERROR:hotlist_panel.py(_update_watchlist_queue:1031): 
更新板块信息到数据库失败: No module named 'instock'
```

**位置**: `hotlist_panel.py:1016`

**原因**: 代码中使用了不存在的 `from instock.core.singleton_stock import stock_manager`

### 问题2: 信号重复显示
**表现**:
1. 同一股票出现多条记录,仅理由不同
2. 同一股票的"大阳涨"信号有多个不同涨幅
3. 双击详情页中重复的信号都归集一条
4. 同一天相似信号多次显示

## 修复方案

### 1. 修复 `instock` 导入错误 ✅

**文件**: `hotlist_panel.py`
**位置**: 第 1013-1031 行

**修改前**:
```python
from instock.core.singleton_stock import stock_manager
mgr = stock_manager.get_instance()
conn = mgr.get_connection('signal_strategy.db')
```

**修改后**:
```python
mgr = SQLiteConnectionManager.get_instance(DB_FILE)
conn = mgr.get_connection()
```

**说明**: 
- 使用已有的 `SQLiteConnectionManager` 替代不存在的 `instock.core.singleton_stock`
- `SQLiteConnectionManager` 在 `db_utils.py` 中定义,已被多处使用(如 `trading_logger.py`)
- 修复了表名错误: `watchlist` → `hot_stock_watchlist`
- 改进了错误日志,添加 `exc_info=False` 避免堆栈信息过多

### 2. 实现跟单队列去重 ✅

**文件**: `trading_hub.py`
**函数**: `get_follow_queue_df()`
**位置**: 第 443-493 行

**去重规则**:
1. **同一股票只保留一条**: 使用 `PARTITION BY code` 窗口函数
2. **优先级排序**: `priority DESC, detected_date DESC, detected_price DESC`
3. **理由合并**: 使用 `GROUP_CONCAT(DISTINCT notes, '; ')` 合并多个入场理由
4. **信号类型合并**: 使用 `GROUP_CONCAT(DISTINCT signal_type, ', ')` 合并信号类型

**SQL 逻辑**:
```sql
WITH ranked_queue AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY code
               ORDER BY priority DESC, detected_date DESC, detected_price DESC
           ) as rn
    FROM follow_queue
    WHERE status NOT IN ('EXITED', 'CANCELLED')
),
merged_notes AS (
    SELECT 
        code,
        GROUP_CONCAT(DISTINCT notes, '; ') as all_notes,
        GROUP_CONCAT(DISTINCT signal_type, ', ') as all_signal_types
    FROM follow_queue
    WHERE status NOT IN ('EXITED', 'CANCELLED')
      AND (notes IS NOT NULL AND notes != '')
    GROUP BY code
)
SELECT 
    rq.*,
    COALESCE(mn.all_notes, rq.notes) as merged_notes,
    COALESCE(mn.all_signal_types, rq.signal_type) as merged_signal_types
FROM ranked_queue rq
LEFT JOIN merged_notes mn ON rq.code = mn.code
WHERE rq.rn = 1
ORDER BY rq.priority DESC, rq.detected_date DESC
```

### 3. 实现观察池去重 ✅

**文件**: `trading_hub.py`
**函数**: `get_watchlist_df()`
**位置**: 第 495-545 行

**去重规则**:
1. **同一股票只保留一条**: 使用 `PARTITION BY code` 窗口函数
2. **优先级排序**: `trend_score DESC, discover_date DESC, pattern_score DESC`
3. **形态描述合并**: 使用 `GROUP_CONCAT(DISTINCT daily_patterns, '; ')` 合并多个发现理由

**SQL 逻辑**:
```sql
WITH ranked_watchlist AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY code
               ORDER BY trend_score DESC, discover_date DESC, pattern_score DESC
           ) as rn
    FROM hot_stock_watchlist
    WHERE validation_status != 'DROPPED'
),
merged_patterns AS (
    SELECT 
        code,
        GROUP_CONCAT(DISTINCT daily_patterns, '; ') as all_patterns
    FROM hot_stock_watchlist
    WHERE validation_status != 'DROPPED'
      AND (daily_patterns IS NOT NULL AND daily_patterns != '')
    GROUP BY code
)
SELECT 
    rw.*,
    COALESCE(mp.all_patterns, rw.daily_patterns) as merged_patterns
FROM ranked_watchlist rw
LEFT JOIN merged_patterns mp ON rw.code = mp.code
WHERE rw.rn = 1
ORDER BY rw.discover_date DESC, rw.trend_score DESC
```

## 预期效果

### 修复前
- ❌ 板块信息更新失败,报 `No module named 'instock'` 错误
- ❌ 跟单队列中同一股票出现多次,理由不同
- ❌ 观察池中同一股票出现多次,形态描述不同
- ❌ 信号日志中大量重复记录

### 修复后
- ✅ 板块信息正常更新到数据库
- ✅ 跟单队列每股只显示一条,理由自动合并 (例: "理由1; 理由2; 理由3")
- ✅ 观察池每股只显示一条,形态描述自动合并
- ✅ 信号类型自动合并 (例: "突破信号, 量价齐升, 新高")
- ✅ UI 显示更清晰,无重复干扰
- ✅ 数据库查询效率提升 (减少数据传输量)

## 验证方法

### 1. 验证导入错误修复
```bash
# 启动程序,观察日志
# 应该不再出现 "No module named 'instock'" 错误
# 板块信息应该正常更新
```

### 2. 验证跟单队列去重
```sql
-- 查看原始数据 (可能有重复)
SELECT code, name, signal_type, notes, detected_date 
FROM follow_queue 
WHERE status NOT IN ('EXITED', 'CANCELLED')
ORDER BY code, detected_date DESC;

-- 查看去重后的数据 (应该每股只有一条)
-- 在程序中打开跟单队列面板,检查是否每股只显示一条
```

### 3. 验证观察池去重
```sql
-- 查看原始数据 (可能有重复)
SELECT code, name, daily_patterns, discover_date, trend_score
FROM hot_stock_watchlist 
WHERE validation_status != 'DROPPED'
ORDER BY code, discover_date DESC;

-- 查看去重后的数据 (应该每股只有一条)
-- 在程序中打开观察池面板,检查是否每股只显示一条
```

### 4. 验证理由合并
- 打开跟单队列,查看 "理由" 列
- 应该看到多个理由用分号分隔: "理由1; 理由2; 理由3"
- 打开观察池,查看 "形态描述" 列
- 应该看到多个形态描述用分号分隔

## 技术细节

### SQLite 窗口函数支持
- SQLite 3.25.0+ 支持窗口函数 (`ROW_NUMBER() OVER (...)`)
- 项目使用的 SQLite 版本应该满足要求
- 如果遇到语法错误,需要升级 SQLite

### GROUP_CONCAT 函数
- SQLite 内置函数,用于字符串聚合
- 默认分隔符为逗号,可自定义 (如 `'; '`)
- `DISTINCT` 关键字自动去除重复值

### 数据完整性
- 去重逻辑不会删除数据库中的原始记录
- 仅在查询时进行去重和合并
- 保留了所有历史信息,便于追溯和分析

## 后续优化建议

### 1. 数据库层面优化
考虑在数据库层面添加唯一约束,从源头避免重复:
```sql
-- 跟单队列: 同一股票同一天只能有一条记录
CREATE UNIQUE INDEX IF NOT EXISTS idx_follow_queue_unique 
ON follow_queue(code, detected_date);

-- 观察池: 同一股票只能有一条活跃记录
-- (需要业务逻辑配合,在插入新记录时更新旧记录状态)
```

### 2. UI 层面优化
- 在详情页中显示信号出现次数
- 添加 "查看所有历史信号" 按钮
- 支持展开/折叠合并的理由

### 3. 性能优化
- 如果数据量很大,考虑添加索引:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_follow_queue_code_status 
  ON follow_queue(code, status);
  
  CREATE INDEX IF NOT EXISTS idx_watchlist_code_status 
  ON hot_stock_watchlist(code, validation_status);
  ```

## 相关文件

- `hotlist_panel.py`: 修复 instock 导入错误
- `trading_hub.py`: 实现跟单队列和观察池去重
- `db_utils.py`: SQLiteConnectionManager 定义
- `trading_logger.py`: 已使用 SQLiteConnectionManager 的示例

## 注意事项

1. **向后兼容**: 修改仅影响数据查询逻辑,不影响数据写入
2. **性能影响**: 窗口函数和 GROUP_CONCAT 会增加查询时间,但数据量不大时影响可忽略
3. **理由顺序**: 合并后的理由顺序不确定,如需特定顺序可修改 SQL
4. **分隔符**: 当前使用 `'; '` 作为分隔符,可根据需要调整

## 测试清单

- [ ] 启动程序,确认无 `No module named 'instock'` 错误
- [ ] 检查板块信息是否正常更新
- [ ] 打开跟单队列,确认每股只显示一条
- [ ] 检查跟单队列的理由是否正确合并
- [ ] 打开观察池,确认每股只显示一条
- [ ] 检查观察池的形态描述是否正确合并
- [ ] 双击股票,查看详情页是否正常
- [ ] 测试添加新信号,确认去重逻辑正常工作
