# ATS Multi-Agent Hub

这是 ATS 项目的轻量文件驱动协作层。GPT/Codex 担任主脑，负责规划、拆解、验收和风险决策；Antigravity 担任执行 Agent，每次只领取一个任务。

## 状态流转

```text
inbox -> running -> done -> review -> archive
                    ^          |
                    |-- rework-|
```

- `inbox/`: 已批准、可领取的任务书。
- `running/`: Agent 已领取且正在实施的任务。
- `done/`: Agent 已提交实现结果，等待主脑审查。
- `review/`: 主脑审查报告。
- `archive/`: 已通过并归档的任务与结果。
- `decisions/`: 跨任务架构决策和上线决策。
- `dashboard/STATUS.md`: 当前进度看板，由脚本生成。
- `events/events.jsonl`: 不可变的状态变更记录。

## 每日使用

```powershell
python tools/agent_hub.py status
python tools/agent_hub.py validate
python tools/agent_hub.py claim 001 --agent antigravity
python tools/agent_hub.py submit 001 --agent antigravity --summary "完成实现和测试"
python tools/agent_hub.py review 001 --decision approved --reviewer codex --summary "验收通过"
python tools/agent_hub.py archive 001
```

本机若 pytest 默认临时目录指向失效盘符，统一使用项目内临时目录：

```powershell
python -m pytest tests/test_agent_hub.py -q --basetemp=.pytest_temp\agent_hub
```

审查不通过时：

```powershell
python tools/agent_hub.py review 001 --decision rework --reviewer codex --summary "补充并发测试"
```

`rework` 会把任务原子地退回 `inbox/`，保留审查报告和事件记录。

## Agent 边界

1. GPT/Codex 只把相互独立、验收条件明确的任务放入 `inbox/`。
2. Antigravity 必须先 `claim`，只修改任务书 `Files Allowed` 中的文件。
3. 每个任务必须附测试命令、测试结果、变更摘要和已知风险。
4. 未经人工批准，不允许自动合并、自动发布或自动实盘下单。
5. `trade_gateway.py`、券商接口、密钥配置和真实下单开关默认属于禁止范围。

## Antigravity 接入

最稳妥的第一阶段是在 Antigravity 中执行以下固定提示：

```text
读取 .agent_hub/AGENT_PROMPT.md，领取 inbox 中编号最小且无依赖阻塞的任务。
严格按任务书实施、测试并提交结果。一次只执行一个任务。
```

如果 Antigravity 后续提供 CLI/API，只需实现一个 adapter 调用上述命令，不需要改变目录协议。
