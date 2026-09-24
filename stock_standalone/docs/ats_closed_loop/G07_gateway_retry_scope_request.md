# G07 Gateway 拒绝重试范围变更请求

状态：串行扩展已实施并通过离线契约回归；本阶段仅由 G07 修改 `trading_kernel/gateway.py` 与 `trading_kernel/tests/test_extension_contracts.py`，其他任务不得并行编辑这两处。

## 复核证据

- `ats/unified_paper_account.py` 为轮动买入腿生成稳定请求键 `<directive_id>:buy`。卖出腿已有订单时，恢复路径会用相同买入腿和请求键重新调用 `execute_command_directive()`。
- 原 `KernelGateway.submit()` 把拒绝响应也当作终态缓存；第一次买入无订单地拒绝后，恢复调用会再次得到旧拒绝，无法根据更新后的状态重新评估。修复后仅复用已接受/执行结果，相同指纹拒绝可重评；指纹仍保留，因此不同 payload 继续返回 `IDEMPOTENCY_CONFLICT`。

## 最小隔离场景

1. PAPER 卖出腿成功并在订单历史可见。
2. 首次轮动买入腿以稳定 ID `<directive_id>:buy` 被拒绝，未产生订单。
3. 重放同一轮动指令；卖出腿应从订单历史恢复且不重复卖出，买入腿应重新通过 Gateway 评估。
4. 若重试通过，只新增一个买入订单；若仍拒绝，应保留最新拒绝，不得伪报成交。相同 ID 不同 fingerprint 仍须 `IDEMPOTENCY_CONFLICT`。

## 所需交接

原 G07 范围包括 `ats/unified_paper_account.py` 和 G07 专项测试；Gateway 与契约回归已串行纳入 G07 子阶段。fake-gateway 3 项与 Gateway 契约 7 项通过；修复仅在隔离 fake service 中验证，不创建默认 kernel service、不连接 PAPER 账户、不读写生产数据。
