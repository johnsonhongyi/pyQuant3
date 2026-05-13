# 任务清单: 解决 send_df 自动推送数据时 Resample 周期未能同步对齐的 Bug

> 创建时间：2026-05-13 18:50  
> 状态：✅ 已完成  
> 目标：当用户在 Tkinter 主端（MonitorTK）切换 resample 周期后，确保其自发推送的实时数据包中携带最新的周期参数，并让可视化界面（Visualizer）在接收并加载数据的同时，秒级自动对齐并渲染到正确的周期面板与显示状态，杜绝多端步调脱节。

---

## 📋 问题回溯与方案设计

### 1. 故障场景
用户反馈在 Tkinter (MonitorTK) 主端切换了 `resample`（如切换到 `3d`）后：
1. Tk 端触发数据刷新并调用 `send_df` 跨进程/Socket 推送数据。
2. 可视化接收到更新后的全量数据并重画界面，但上方工具栏的 `resample` 状态依旧锁死在旧状态（例如 `'d'`）。
3. 这产生了实质性的“界面绘制的数据格式与显示的文字周期不一致”的割裂体验。

### 2. 原理剖析
- **发送协议缺省**：`instock_MonitorTK.py` 中的 `send_df` 方法在组装封装字典 `sync_package` 时，仅仅包含 `'type'`, `'data'`(DataFrame) 以及 `'ver'` 三个字段。**并未**将当前 Tk 生效的全局配置 `self.global_values.getkey("resample")` 封装进去。
- **接收端被动盲目**：`trade_visualizer_qt6.py` 中的数据流入口 `on_dataframe_received` 仅负责对 DataFrame 数据进行更新与差分应用，缺乏对周期维度的解析与反向对齐机制。

### 3. 实施优化策略
- **✅ 数据包扩充**：在 `send_df` 打包环节增加 `'resample': cur_resample`。
- **✅ 消费端联动**：在 `on_dataframe_received` 解析完版本号后，提取该 `'resample'` 键值。
- **✅ 脏检查秒级对齐**：当捕获到的推送周期与可视化当前 `self.resample` 不一致时，主动触发 `self.on_resample_changed(target_res_clean)`，从而同时更新 UI 的 ComboBox 和底层的 K线重载队列。

---

## 🛠️ 实施步骤记录

### 第一阶段：修改 MonitorTK 主程序发送逻辑
- [x] **字段提取**：定位 `instock_MonitorTK.py` 的 `send_df` 循环（第 5692 行附近）。
- [x] **协议注入**：在 `sync_package` 构建阶段，通过 `self.global_values.getkey("resample")` 提取当前激活周期，统一进行 `.lower().strip()` 标准化，将其写入协议字段。

### 第二阶段：重构 Visualizer 解析与分流器（Socket 双轨保障）
- [x] **双轨捕获：Socket 管道**：定位 `trade_visualizer_qt6.py` 中的 `on_dataframe_received` 方法（第 8523 行附近），提取 `df.get('resample')`。
- [x] **双轨捕获：主 Pipe 管道 [关键发现]**：查明系统在 MonitorTK 直接调起时使用 multiprocessing Connection。故在 `_poll_command_queue` 的 `UPDATE_DF_DATA` 指令处理支路中（第 6059 行），也同步注入 `payload.get('resample')` 解析逻辑，彻底完成管道全覆盖。
- [x] **对齐条件控制与触发联动**：引入本地自检 `if current_resample != target_res_clean:`，当检测到失配时一站式执行 `self.on_resample_changed` 彻底修复脱节。
- [x] **🌟 时序逻辑深度加固 [极致一致性]**：基于用户“数据先正确刷新，再更新周期显示”的强力工程约束，针对双通道进行了因果时序调优：
    - **Pipe 管道**：将解析动作推迟到 `self.df_all` 物理载入内存并置位 `data_updated = True` 之后才开闸执行。
    - **Socket 管道**：将触发代码封装在 `_safe_process` 和 `_safe_apply_diff` 的异步回调尾部，只有当 DataFrame 在可视化底层**物理渲染更新全部成功**后，才安全触发 UI 对齐。这从原理上杜绝了用“新周期”去配“旧数据”的错帧 bug。

---

## 📊 收益评估与总结

1. **实现数据与周期的全双工物理绑定**：推送数据不仅是简单的推送行列矩阵，而是将“产生这批矩阵的运行上下文参数（Resample）”也同时投递过去，形成了彻底的数据状态闭环。
2. **消除了用户交互疑惑**：无论用户是在可视化端手动调整，还是在 MonitorTK 切换后让推送机制全盘刷写，两端都能在极短的百毫秒级周期内做到“眼见即所得”，保障了量化看板高度的信息保真。
