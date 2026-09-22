# Agent Hub 显式执行策略

## 使用方式

```text
@agenthub /plan <任务描述>
```

只创建/准备 Agent Hub 任务书，不修改业务代码。

```text
@agenthub /run <Task-ID> /confirm agenthub
```

明确授权后才允许执行。确认前的所有开发请求都必须停留在规划、审计或测试准备阶段。

## 机器门禁

```powershell
python -m tools.agenthub_command "@agenthub /run 025 /confirm agenthub"
```

门禁状态写入 `.agent_hub/events/command_gate.json`。只有 `decision=EXECUTE_ALLOWED`
才能调用 Agent Hub 的 `execute`/`execute_batch`；否则只能调用 `preview`。

后台执行（脱离当前会话）：

```powershell
python -m tools.agenthub_command --start-background "@agenthub /run 025 /confirm agenthub"
```

该命令会启动独立 Orchestrator 和监督进程。运行状态、心跳、PID、日志和最终报告保存在
`.agent_hub_runtime/`；即使聊天窗口关闭，任务仍继续，完成后生成 `run_*_report.md`。

## 强制闭环

执行必须经过 `.agent_hub/inbox -> running -> review -> done/archive`，并保留测试证据、
范围检查、`agent_report.json` 和 Codex 审查结论。临时协作 Agent 不得替代正式 Agent Hub 闭环。
