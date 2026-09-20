# Decision 000: 采用文件驱动多 Agent 控制面

- Date: 2026-09-20
- Status: APPROVED
- Scope: 开发协作，不涉及自动实盘

采用 `.agent_hub` 作为 GPT/Codex 与 Antigravity 的共享控制面。第一阶段限制并发任务数为 1，所有实现必须经过 GPT/Codex 审查；自动合并、自动实盘买入和自动实盘卖出全部关闭。

只有在一次完整演练稳定后，才评估 Antigravity CLI/API adapter 和自动轮询器。
