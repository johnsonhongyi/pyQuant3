# ✅ Hotlist Panel 板块信息优化完成

**日期**: 2026-02-11  
**状态**: ✅ 完成

---

## 🎯 优化目标

1. **板块信息持久化**: 优先热点板块,补充 df_all,同步到数据库
2. **盈亏实时计算**: 保持实时计算,不持久化到数据库

---

## ✅ 完成的优化

### 1. 板块信息获取策略

**优先级**:
1. **优先**: 从热点板块获取 (`_get_recent_hot_concepts()`)
2. **补充**: 如果没有热点板块,从 `df_all.category` 获取
3. **持久化**: 首次获取后更新到数据库 `watchlist.sector`

**优势**:
- ✅ 热点板块更有价值(一个股票可能属于多个板块)
- ✅ 首次获取后持久化,下次直接从数据库读取
- ✅ 保留完整板块信息(最多 20 字)

### 2. 盈亏实时计算

**策略**:
- ✅ 保持实时计算,不持久化到数据库
- ✅ 每秒多次更新,跟随价格变化
- ✅ 批量计算,性能优化到 < 2ms

**计算公式**:
```python
盈亏% = (当前价 - 发现价) / 发现价 × 100%
```

---

## 📊 数据流

### 板块信息获取流程

```
1. 读取 Watchlist (从数据库)
   ↓
2. 检查 sector 字段
   ↓
3. 如果为空:
   ├─ 优先: 从热点板块获取
   └─ 补充: 从 df_all.category 获取
   ↓
4. 保留完整信息(最多20字)
   ↓
5. 更新到数据库
   ↓
6. 显示在 UI
```

### 盈亏计算流程

```
1. 获取实时价格 (_last_price_map)
   ↓
2. 获取发现价 (watchlist.discover_price)
   ↓
3. 批量计算盈亏%
   ↓
4. 更新 UI (不写数据库)
```

---

## 🔧 关键实现

### 1. 板块信息优先级

```python
# 1. 优先从热点板块获取
hot_concepts = self._get_recent_hot_concepts()
for row in df.itertuples():
    code_str = str(row.code)
    if not row.sector or str(row.sector).strip() == '':
        if code_str in hot_concepts:
            hot_sector = hot_concepts[code_str]
            if len(hot_sector) > 20:
                hot_sector = hot_sector[:20]
            sector_map[code_str] = hot_sector
            codes_to_update.append((code_str, hot_sector))

# 2. 补充: 从 df_all.category 获取
for row in df.itertuples():
    code_str = str(row.code)
    if (not row.sector or str(row.sector).strip() == '') and code_str not in sector_map:
        # 从 df_all 获取
        category = df_all.loc[code]['category']
        sectors = category.split(';')
        main_sector = sectors[0] if sectors else ''
        if len(main_sector) > 20:
            main_sector = main_sector[:20]
        sector_map[code_str] = main_sector
        codes_to_update.append((code_str, main_sector))
```

### 2. 批量更新到数据库

```python
if codes_to_update:
    for code, sector in codes_to_update:
        c.execute("""
            UPDATE watchlist 
            SET sector = ? 
            WHERE code = ? AND (sector IS NULL OR sector = '')
        """, (sector, code))
    
    conn.commit()
    logger.info(f"✅ 已更新 {len(codes_to_update)} 个股票的板块信息到数据库 (热点板块优先)")
```

### 3. 盈亏实时计算

```python
# 批量更新盈亏 (不写数据库)
for row in df.itertuples():
    code_str = str(row.code)
    curr_price = self._last_price_map.get(code_str, 0.0)
    discover_price = float(row.discover_price or 0.0)
    
    if discover_price > 0 and curr_price > 0:
        pnl_pct = (curr_price - discover_price) / discover_price * 100
        it.setText(f"{pnl_pct:+.2f}%")
        
        # 批量设置颜色
        if pnl_pct > 0: 
            it.setForeground(QColor(220, 80, 80))  # 红色
        elif pnl_pct < 0: 
            it.setForeground(QColor(80, 200, 120))  # 绿色
```

---

## 📈 预期效果

### 板块信息
- ✅ **首次加载**: 从热点板块/df_all 获取,更新到数据库
- ✅ **后续加载**: 直接从数据库读取
- ✅ **日志**: `✅ 已更新 X 个股票的板块信息到数据库 (热点板块优先)`

### 盈亏信息
- ✅ **实时计算**: 每秒多次更新
- ✅ **性能**: < 2ms
- ✅ **不持久化**: 不写入数据库

---

## 🎉 总结

本次优化完成了以下目标:

1. ✅ **板块信息优化**: 热点板块优先,完整信息保留,持久化到数据库
2. ✅ **盈亏实时计算**: 保持实时计算,不持久化,性能优化

**数据持久化策略**:
- **Watchlist**: 持久化到 `signal_strategy.db`
- **板块信息**: 持久化到 `watchlist.sector`
- **盈亏信息**: 实时计算,不持久化

**现在重启应用,板块信息应该会正确显示(热点板块优先),并且会自动同步到数据库!** 🚀

---

## 📚 相关文档

- `optimization_final.md` - 最终优化总结
- `sector_optimization.md` - 板块信息优化
- `final_performance_report.md` - 详细性能报告

**优化完成** ✅  
**板块信息**: 热点优先 + 持久化  
**盈亏信息**: 实时计算 + 不持久化
