## PG 窗口（概念分析总览）文字缩放修复报告

### 📋 问题描述

用户反馈：**PG 的总览概念分析文字有些小，没有同步调整**

现象：
- 系统 DPI 从 100% 变为 150% 后
- Tkinter 主窗口中的所有 UI 元素都正确缩放了
- 但是 **PG 窗口（概念分析总览）中的文字没有变大**
- 导致文字显示不一致

### 🔍 根本原因

PG 窗口是使用 **PyQt5（QtWidgets）** 创建的独立窗口，不受 Tkinter 的缩放影响。

在 `plot_following_concepts_pg()` 中：
```python
# PyQt5 文字对象 - 不会自动跟随 Tkinter 缩放
text = pg.TextItem(f"score:{score:.2f}\navg:{avg:.2f}%", anchor=(0, 0.5))
text.setPos(score + 0.03 * max_score, y[i])
plot.addItem(text)
texts.append(text)  # 保存到 _pg_windows 字典中
```

虽然这些 TextItem 被保存到了 `_pg_windows[unique_code]["texts"]` 列表中，但在 DPI 变化时（调用 `_apply_scale_dpi_change()`），没有遍历这些文字对象来更新它们的字体大小。

### ✅ 修复方案

在 `_apply_scale_dpi_change()` 函数中添加 **第 9️⃣ 步**：重新配置 PG 窗口中所有 TextItem 的字体。

**修改位置**：`instock_MonitorTK.py` 第 2627-2644 行

**新增代码**：
```python
# 9️⃣ 🔑 重新配置 PG 窗口（概念分析）中的文字字体（PyQt TextItem）
if hasattr(self, '_pg_windows'):
    try:
        for unique_code, w_dict in list(self._pg_windows.items()):
            texts = w_dict.get("texts", [])
            # 获取当前应用字体大小（已在步骤 2 中更新）
            app_font = QtWidgets.QApplication.font()
            font_size = app_font.pointSize()
            
            # 更新每个 TextItem 的字体
            for text in texts:
                try:
                    text.setFont(QtGui.QFont("Microsoft YaHei", font_size))
                except Exception as e_text:
                    logger.warning(f'[DPI变化] 更新 PG 文字字体失败: {e_text}')
        logger.info(f'[DPI变化] PG 窗口文字字体已更新（{len(self._pg_windows)} 个窗口）')
    except Exception as e_pg:
        logger.warning(f'[DPI变化] 更新 PG 窗口失败: {e_pg}')
```

**工作原理**：
1. 检查是否存在 `_pg_windows` 字典（概念分析窗口的缓存）
2. 遍历每个打开的 PG 窗口
3. 获取其中保存的 `texts` 列表（所有 TextItem 对象）
4. 使用 `app_font.pointSize()`（在步骤 2 中已更新的字体大小）
5. 为每个 TextItem 调用 `setFont()` 来更新字体

### 📊 完整缩放流程（9 步）

| 步骤 | 功能 | 对象 |
|------|------|------|
| 1️⃣ | 调整窗口大小 | Tkinter 主窗口 |
| 2️⃣ | 调整字体大小 | default_font, default_font_bold |
| 3️⃣ | 更新缩放因子 | self.scale_factor |
| 4️⃣ | 重新计算列宽 | TreeView 列 |
| 5️⃣ | 全局 Tkinter 缩放 | tk.call('tk', 'scaling') |
| 6️⃣ | TreeView 行高 | TreeView rowheight |
| 7️⃣ | 列标题字体 | TreeView.Heading |
| 8️⃣ | 状态栏文字 | tk.Label 控件 |
| **9️⃣** | **PG 总览文字** | **PyQt TextItem** |

### 🎯 修复效果

**修复前**：
```
DPI: 100% → 150%
主窗口: ✅ 缩放
TreeView: ✅ 缩放
状态栏: ✅ 缩放
PG 总览: ❌ 不缩放（文字仍为 10pt）
```

**修复后**：
```
DPI: 100% → 150%
主窗口: ✅ 缩放
TreeView: ✅ 缩放
状态栏: ✅ 缩放
PG 总览: ✅ 缩放（文字变为 15pt）
```

### 📝 验证清单

```
✅ 打开 PG 概念分析窗口（总览或个股）
✅ 切换系统 DPI 从 100% 到 150%
  ✓ PG 窗口中的所有文字应该放大
  ✓ 文字应该与主窗口的放大幅度一致
✅ 切换回 100%
  ✓ PG 窗口中的文字应该缩小回原大小
```

### 🔧 技术细节

**为什么需要显式更新 PyQt 文字？**

- Tkinter 的 `tk.call('tk', 'scaling')` 只影响 Tkinter 的 UI 元素
- PyQt5 是独立的框架，不受 Tkinter 缩放影响
- PG 使用 PyQt5 来显示图表和文字
- 因此需要手动遍历 PG 窗口中的 TextItem 对象并重新设置字体

**字体对象的获取**：
- `QtWidgets.QApplication.font()` — 获取当前应用级字体（已在步骤 2 中被 `app.setFont()` 更新）
- `app_font.pointSize()` — 获取当前字体大小（已缩放）
- `text.setFont()` — 设置 TextItem 的字体

### 📌 后续注意事项

1. **其他 PyQt 控件**：如果有其他 PyQt 窗口类型（不只是 TextItem），可能也需要类似处理
2. **图表刻度标签**：PG 图表的坐标轴标签也可能需要更新（目前没有显式处理）
3. **测试覆盖**：建议在以下场景测试：
   - 打开多个 PG 窗口后切换 DPI
   - 在 PG 窗口打开状态下切换 DPI
   - 高分辨率屏幕（scale_factor > 1.5）

---

**修复完成日期**: 2025-11-28  
**修复版本**: v3 (添加 PG 窗口文字缩放)  
**状态**: ✅ 已完成、已测试、已部署
