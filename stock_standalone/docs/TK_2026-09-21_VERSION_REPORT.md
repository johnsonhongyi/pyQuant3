# TK 2026-09-21 版本说明

## 版本定位

本版本将 Trading Kernel 固化为“稳定打包主链”。TK 主程序可以一次打包后长期运行，ATS、策略插件、状态服务和未来券商模块通过版本化 Gateway 接入，不再依赖 TK 内部类、内部字段或内部执行流程。

当前仍以 PAPER 为验证主账户；本版本没有连接券商，也没有开启真实自动下单。

## 本次落地内容

### 1. 版本化决策契约

新增 `trading_kernel/contracts.py`，固定 API `1.0`：

- `DecisionRequest`：代码、动作、价格、仓位比例、策略来源、特征和请求号。
- `DecisionResponse`：接受状态、执行状态、动作、执行比例、Trace ID、Order ID、拒绝原因和状态。
- `StrategyProvider`：外部策略只需实现 `decide(signal, state)`。
- `StateStore`：外部状态服务实现 `get/set/snapshot`。
- `EventSink`：外部审计系统实现 `append(record)`。

请求的主版本不一致时，在进入内核前直接返回 `INCOMPATIBLE_API_VERSION`，避免旧插件破坏主链。

### 2. 固定公共入口 KernelGateway

`trading_kernel/gateway.py` 是 ATS、TK UI 和未来模块唯一推荐入口：

- `submit(DecisionRequest)`：类型安全的内存调用。
- `submit_mapping(payload)`：适合 JSON、命名管道或进程间传输；未知字段会被忽略。
- `capabilities()`：返回 API 版本、内核版本、运行模式、动作集合和扩展端口，供启动握手与自动对齐使用。
- `get_positions()`、`get_account_snapshot()`、`get_order_history()`、`get_state_snapshot()`：统一读模型。
- `reconcile_state()`：以当前执行账户持仓对齐 TK 状态机。

### 3. 四类运行时扩展接口

TK 服务保留以下注册入口，不需要修改已打包的决策引擎：

- `register_strategy_provider(provider)`：挂接新策略。
- `register_execution_adapter(mode, adapter)`：挂接 PAPER、CONFIRM 或 LIVE_AUTO 执行适配器。
- `register_state_store(store)`：切换状态存储；默认迁移现有状态并重新对齐持仓。
- `register_event_sink(sink)`：切换审计流水输出，同时同步 CONFIRM 和 LIVE_AUTO 包装器。

执行适配器必须提供 `submit_order`、`cancel_order`、`get_positions` 和 `get_account_snapshot`，注册时即校验接口，不满足契约的模块会被拒绝。

详细接入约束见 [trading_kernel/EXTENSION_API.md](../trading_kernel/EXTENSION_API.md)。

### 4. ATS 统一通过 TK PAPER 主链

`ats/unified_paper_account.py` 不再直接访问 `TradingKernelService` 或其内部 PAPER 适配器：

- 订单、持仓、账户和流水均通过 `KernelGateway` 读取。
- 交易指挥室命令通过 `DecisionRequest` 提交。
- 执行完成后根据统一 `DecisionResponse` 返回 Trace ID、Order ID、拒绝原因和执行比例。
- 持仓读取后通过 Gateway 触发状态自动对齐。

这样可以保证 ATS 展示的持仓、TK 状态机、订单历史和收益统计来自同一条 PAPER 主链。

### 5. 一次打包后的模块完整性

`ats.spec`、`instock_MonitorTK.spec`、`instock_MonitorTK-ondir.spec` 和 `instock_MonitorTK-setuptools.spec` 均使用 `collect_submodules('trading_kernel')`，确保 Gateway、contracts、执行适配器、状态和审计模块不会因动态导入在打包后缺失。

## 兼容与安全边界

- 同一主版本内允许增加可选字段和能力；已有字段含义保持不变。
- `OBSERVE`、`PAPER`、`CONFIRM`、`LIVE_AUTO` 模式仍由 TK 风控、状态机、幂等和审计链控制。
- 注册执行适配器不会绕过风险闸门，也不会自动开启真实交易。
- PAPER 账户仍是当前验收阶段的权威账户；券商模块仅保留接口，不在本版本实现。

## 验证结果

| 验证项 | 结果 |
| --- | --- |
| 接口契约、边界、纸盘、风控和统一账户测试 | 25 passed |
| TK 全量测试 | 46 passed，1 个历史预期失败 |
| Python 编译检查 | passed |
| 四份 PyInstaller spec 语法检查 | passed |
| `git diff --check` | passed |

历史预期失败为 `test_kernel_service_order_routing_by_mode`：旧测试预期 `SECTOR_FOCUS` 信号自动 BUY，而当前策略规则返回 `NON_MINED_IGNORE/HOLD`。该差异不涉及本次 Gateway、契约或打包改造，后续应单独更新测试夹具或策略预期。

## 后续接入顺序

1. 继续用 PAPER 完成策略收益、回放一致性和状态对齐验收。
2. 由策略模块实现 `StrategyProvider`，通过能力握手确认 API 主版本。
3. 由券商模块实现 `ExecutionAdapter`，先接入 CONFIRM，再进行小额人工验证。
4. 只有 PAPER 与 CONFIRM 指标稳定后，才评估 LIVE_AUTO；本版本不改变该安全门槛。
