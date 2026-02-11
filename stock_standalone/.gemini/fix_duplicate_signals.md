# 信号去重与优化方案

## 问题分析

### 问题1: `instock` 模块导入错误
**错误信息**: `No module named 'instock'`
**位置**: `hotlist_panel.py:1016`
**原因**: 代码中使用了 `from instock.core.singleton_stock import stock_manager`,但该模块不存在

### 问题2: 信号重复显示
**表现**:
1. 同一股票出现多条记录,仅理由不同
2. 同一股票的"大阳涨"信号有多个不同涨幅
3. 双击详情页中重复信号未归集
4. 同一天相似信号多次显示

**涉及表**:
- `signal_message`: 存储所有信号记录
- `follow_queue`: 跟单队列
- `hot_stock_watchlist`: 观察池

## 解决方案

### 1. 修复 instock 导入错误

**方案**: 使用已有的 `SQLiteConnectionManager` 替代 `instock.core.singleton_stock`

```python
# 原代码 (错误)
from instock.core.singleton_stock import stock_manager
mgr = stock_manager.get_instance()
conn = mgr.get_connection('signal_strategy.db')

# 修复后
mgr = SQLiteConnectionManager.get_instance(DB_FILE)
conn = mgr.get_connection()
```

### 2. 信号去重策略

#### 2.1 数据库层面去重

**信号日志 (signal_message)**:
- 同一股票同一天的相同信号类型,合并理由
- 保留最高优先级/最高分数的记录
- 使用 `GROUP BY code, created_date, signal_type`

**跟单队列 (follow_queue)**:
- 同一股票只保留最新的跟踪记录
- 使用 `UNIQUE(code, detected_date)` 约束

**观察池 (hot_stock_watchlist)**:
- 同一股票只保留一条记录
- 合并多个发现理由

#### 2.2 UI层面去重

**信号日志显示**:
- 同一股票同一天只显示最重要的2条信号
- 按优先级和分数排序
- 合并相似理由

**跟单队列显示**:
- 同一股票只显示一条记录
- 合并多个入场理由

**详情页显示**:
- 归集重复信号
- 显示信号出现次数
- 合并理由文本

### 3. 实施步骤

#### Step 1: 修复导入错误
- 替换 `instock` 导入为 `SQLiteConnectionManager`
- 测试板块信息更新功能

#### Step 2: 数据库去重查询
- 创建去重查询函数
- 实现理由合并逻辑
- 实现信号优先级排序

#### Step 3: UI去重显示
- 修改信号日志查询逻辑
- 修改跟单队列查询逻辑
- 修改详情页显示逻辑

#### Step 4: 测试验证
- 验证导入错误已修复
- 验证信号不再重复
- 验证理由正确合并

## 实施细节

### 信号合并规则

1. **相同信号定义**:
   - 同一股票 (code)
   - 同一天 (created_date)
   - 相同信号类型 (signal_type)

2. **理由合并**:
   - 使用分号分隔: `理由1; 理由2; 理由3`
   - 去除重复理由
   - 最多显示前3个理由

3. **优先级规则**:
   - 优先级高的优先
   - 分数高的优先
   - 时间新的优先

4. **显示限制**:
   - 信号日志: 每股每天最多2条
   - 跟单队列: 每股1条
   - 详情页: 归集显示,标注次数

### SQL查询示例

```sql
-- 信号日志去重查询 (每股每天最多2条)
WITH ranked_signals AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY code, DATE(created_date)
               ORDER BY priority DESC, score DESC, timestamp DESC
           ) as rn
    FROM signal_message
    WHERE created_date >= ?
)
SELECT 
    code,
    name,
    signal_type,
    GROUP_CONCAT(DISTINCT reason, '; ') as reasons,
    MAX(score) as max_score,
    MAX(priority) as max_priority,
    COUNT(*) as signal_count,
    MAX(timestamp) as latest_time
FROM ranked_signals
WHERE rn <= 2
GROUP BY code, DATE(created_date), signal_type
ORDER BY max_priority DESC, max_score DESC, latest_time DESC;
```

```sql
-- 跟单队列去重查询 (每股1条)
SELECT 
    code,
    name,
    signal_type,
    GROUP_CONCAT(DISTINCT notes, '; ') as merged_notes,
    MAX(detected_price) as latest_price,
    MAX(detected_date) as latest_date,
    status
FROM follow_queue
WHERE status = 'TRACKING'
GROUP BY code
ORDER BY MAX(priority) DESC, MAX(detected_date) DESC;
```

## 预期效果

1. ✅ 修复 `instock` 导入错误
2. ✅ 同一股票同一天的相同信号合并显示
3. ✅ 理由自动归集,避免重复
4. ✅ 跟单队列每股只显示一条
5. ✅ 详情页信号归集显示
6. ✅ 提升UI响应速度和可读性
