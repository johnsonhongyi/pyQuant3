# G07 TK PAPER 指令关联

状态：源码与定向离线专项通过；线上 PAPER 观察未完成，发布仍阻断。  
实施前核验：`KernelGateway.submit()` 已按 `request_id` 幂等缓存，PAPER adapter 订单保留请求 ID；ATS 路由此前未传指令 ID，重复请求也未回读既有订单。

## 本次变更

- `execute_command_directive()` 将 ATS `directive_id` 作为 TK `request_id`，并传递 candidate/plan/exit rule、strategy_tag、tide_state、cross_day_state 元数据；有值时经 `DecisionRequest.to_kernel_item()` 保留到 TK 输入。
- TK signal_canonicalizer 已将 directive/candidate/plan/exit rule/strategy/tide/cross-day 字段加入显式特征白名单；孤立 HOLD-only Gateway 回归确认字段贯通至 JSONL 中的 signal.features。
- 2026-09-24 追加隔离回归验证三类决策维度透传；当前上游尚未为所有指令填充潮汐/跨日字段，因此这项修复不改变 G13 真实样本的既有不合格结论，仍需在 G06/G08 生产指令时捕获当时上下文并用真实 PAPER 轨迹验收。
- 重试时可按 `request_id` 在 TK 订单历史中恢复已存在的订单结果，不依赖订单数量增长。
- 执行结果扩展 request、execution、status 字段；ATS 成功路由后更新 `audit_envelope` 的状态、数量和订单标识。
- 全仓轮动卖出腿/买入腿使用稳定的 `:sell` / `:buy` 子请求 ID，维持两个 TK 动作各自幂等。
- 父级审计 envelope 保存两腿订单回执；卖出成功而买入失败时标为 PARTIAL，并保留两腿 request/order/execution/status。
- `KernelGateway` 对同指纹的已接受/已执行结果保持幂等缓存；拒绝回执保留指纹以拦截不同 payload，但相同 payload 会重新评估，避免轮动买入腿永久复用旧拒绝。
- 指挥室对账投影使用 TK read model 的内核状态、订单流水状态和 PAPER 恢复就绪字段；同时独立比较快照与订单推导的持仓代码集合及共有持仓股数。即使上游误报 `ALIGNED`，代码或股数不一致仍返回 `RECONCILIATION_MISMATCH` 并列出差异；缺少内核报告或恢复就绪字段也 fail-closed；显式空/无效 read model 不会隐式回退读取默认网关。
- G07 指令/对账专项 9 passed；Gateway 契约专项 7 passed，覆盖拒绝后重试成功、成功后幂等复用、拒绝后不同 payload 冲突、并发和 FIFO/跨日缓存行为，以及恢复阻断/内核报告缺失不会显示对齐。

## 验收与限制

- 复验命令 `python -m pytest tests/test_g07_paper_directive_link.py tests/test_g10_ui_execution_gate.py -q`：13 passed；其中 G07 指令/对账 9 passed、G10 UI 4 passed；Gateway 选定契约回归：7 passed。以上均使用隔离 fake service，不连接 PAPER 账户。
- TK 逐笔审计、多腿部分成交及重启后的真实订单回读仍须在独立 PAPER 环境验收。
- 线上逐笔审计和连续 PAPER 观察未完成；`ATS_RECEIVED` 仍不作为成交证据。

