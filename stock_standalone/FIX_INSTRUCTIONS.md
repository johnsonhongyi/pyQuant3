# 修复说明

当前代码中有两个方法：

1. `_update_plot_title(self, code, day_df, tick_df)` - 完整更新标题，在 render_charts 中调用
2. `_refresh_sensing_bar(self, code)` - 仅刷新监理看板，在 update_df_all 中调用

## 当前正确的调用方式：

### 在 render_charts 中（第1627行）：
```python
self._update_plot_title(code, day_df, tick_df)
```

### 在 update_df_all 中（第1508行）：
```python
self._refresh_sensing_bar(self.current_code)
```

## 如果仍然报错，请检查：

1. 确保文件已保存
2. 重启可视化器进程
3. 检查是否有多个 trade_visualizer_qt6.py 文件

## 如果错误仍然存在，可以临时修改 update_df_all：

```python
def update_df_all(self, df=None):
    if df is not None:
        self.df_cache = df.copy() if not df.empty else pd.DataFrame()
        self.df_all = self.df_cache
    self.update_stock_table(self.df_all)
    
    # 临时注释掉标题刷新，先确保基本功能正常
    # if getattr(self, 'current_code', None) and hasattr(self, 'kline_plot'):
    #     self._refresh_sensing_bar(self.current_code)
```

然后在 render_charts 中手动点击股票时会更新标题。
