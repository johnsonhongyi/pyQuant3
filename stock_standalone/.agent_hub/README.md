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
6. GPT/Codex负责总体架构、任务拆解、代码审查、测试闸门和版本决策；Antigravity负责按任务实施或独立审计并提交证据，双方不得互相冒充验收角色。
7. 业务节点必须完成“Antigravity Worker交付 -> 自动测试与范围检查 -> Codex审查 -> 中文版本报告与Git提交”的闭环后，才能标记为完成。
8. Codex直接实现的业务代码必须标记为“待Antigravity独立复核”，不能仅凭Codex自测宣称双Agent验收通过。
9. 主控、执行端、权限分层和输出格式统一遵守 `.agent_hub/PROMPT_PROTOCOL.md`；该文件是工程协议，不是写作建议。

## Worker异常处理

Antigravity发生连接、代理、认证、权限、CLI参数、沙箱或配置异常时，必须按以下顺序处理：

1. 保留任务状态、CLI原始日志和失败类型，不归档、不跳过。
2. 修复Clash路由、OAuth登录、非交互权限、CLI配置或Orchestrator适配问题。
3. 依次运行 `preflight --require-auth`、最小只回复回声测试和原任务预演。
4. 恢复后继续执行原任务，再进入测试闸门和Codex审查。

短暂故障不允许改成Codex单Agent长期代做。只有CLI或服务明确返回配额耗尽、速率限额或账户额度不可用，并保存错误日志作为证据时，任务才可标记为“限额阻塞”；额度恢复后继续原闭环。限额期间Codex可继续设计、拆解、审查和准备测试，但任何直接业务实现仍须补做Antigravity独立复核。

## Antigravity 接入

最稳妥的第一阶段是在 Antigravity 中执行以下固定提示：

```text
读取 .agent_hub/AGENT_PROMPT.md，领取 inbox 中编号最小且无依赖阻塞的任务。
严格按任务书实施、测试并提交结果。一次只执行一个任务。
```

如果 Antigravity 后续提供 CLI/API，只需实现一个 adapter 调用上述命令，不需要改变目录协议。

## 全自动编排（方式 C / C1）

本机已接入 `agy.exe` 执行 Agent 和 `codex.exe` 主脑审查。先预演，再显式执行：

```powershell
python tools/agent_orchestrator.py preflight
python tools/agent_orchestrator.py run --task 001
python tools/agent_orchestrator.py preflight --require-auth
python tools/agent_orchestrator.py run --task 001 --execute
```

认证探针应在启动批次前运行一次；批次内每个任务只执行本地二进制与 Hub 检查，避免重复消耗模型调用和受短暂认证波动影响。

执行链为：

```text
选择任务 -> 原子领取 -> Antigravity sandbox 实施 -> 白名单测试
        -> 文件越界检查 -> Codex 只读审查 -> merge report
```

安全默认值：

- Antigravity 非交互模式连 `ListDir` 也要求确认。`worker_auto_approve_permissions` 默认关闭；启用它会批准该 Agent 的全部工具请求，必须由用户明确授权。
- 权限按 `.agent_hub/PROMPT_PROTOCOL.md` 的 P0_READONLY、P1_DOCS_SAFE、P2_CODE_LOW、P3_CODE_MEDIUM、P4_RELEASE_GATE、P5_FORBIDDEN 分层判定；任务风险、工具类别和文件范围任一越界都降级为人工确认或拒绝。
- 即使用户明确开启自动权限，编排器也仅允许不高于 `max_auto_approve_risk` 的任务使用，并继续强制 CLI `--sandbox`、范围检查和测试闸门。
- 用户已批准研发流水线连续推进至 `MEDIUM` 风险；`HIGH`、真实下单、密钥、自动合并和实盘开关仍禁止自动执行。
- 不自动归档，不自动合并，不自动实盘。
- Worker 失败时任务保留在 `running/` 等待诊断，不继续下一任务。
- Worker因连接、代理、认证、权限或CLI故障失败时，先修复Antigravity执行能力并重试原任务；除有日志证明的限额耗尽外，不得跳过Worker闭环。
- 测试或越界检查失败时强制 `REWORK`。

配置位于 `orchestrator.json`。Worker 使用已验证的 `gemini-3.8-flash-high`，并仅为 Antigravity 子进程注入 Clash `127.0.0.1:7897`；ATS、TDX 和其他交易进程不受影响。Codex 继续负责最终只读审查。


## 2026-09-21 并行执行与三层审查升级

Agent Hub 不再以“全局单 running 任务”为默认瓶颈。控制面现在允许最多 3 个 running 任务，但只有同时满足以下条件才可并行：
- `Depends-On` 已全部完成并通过审查；
- `Files Allowed` 与其他 running 任务无重叠；
- Orchestrator 批处理默认 2 个 Worker，上限 3 个；
- 并行期间 scope check 会识别其他已授权任务拥有的文件，避免把合法并发改动误判为当前任务越界。

推荐入口：
```powershell
python tools/agent_orchestrator.py run-batch
python tools/agent_orchestrator.py run-batch --execute --max-workers 2
python tools/agent_orchestrator.py checkpoint-review --node P1 --tasks 010 011
python tools/agent_orchestrator.py release-gate --release v2026.09.22 --checkpoints P1 P2 P3
```

审查额度分层固定为：
- `task_review`：fast/light，仅做单任务正确性与范围审查；
- `p_checkpoint_review`：Medium，仅在节点内所有任务已 APPROVED 后调用一次；
- `release_gate`：High，仅在全部指定 P 节点通过后调用一次。

P 节点自动生成 `VERSION_REPORT_ZH.md` 与 `COMMIT_MESSAGE_ZH.txt`。自动合并、自动 Git commit/tag、真实交易权限仍保持关闭。
