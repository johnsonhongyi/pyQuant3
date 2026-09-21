# Agent Hub 多Agent控制面升级版本记录（2026-09-21）

## 1. 升级目标
解除全局单 running 任务的串行瓶颈，在不放宽交易风控和文件范围保护的前提下，引入依赖 DAG、文件所有权互斥、2~3 Worker 批处理，以及 task / P checkpoint / Release Gate 三层审查。

## 2. 并行执行机制
- Hub 最大 running 任务提升到 3，默认批处理 Worker=2，上限=3。
- Depends-On 未满足时禁止 claim。
- Files Allowed 同时承担修改白名单与并行文件所有权声明。
- 两个任务的 Files Allowed 存在重叠时禁止并发领取。
- batch 模式下 scope check 能识别其他已授权并发任务拥有的文件，避免合法并发修改被误判为当前任务越界。
- 仍禁止同一业务文件同时存在两个写所有者。

## 3. 三层审查与额度控制
- task_review：GPT-5.6 Luna / low，仅做普通任务正确性、范围和测试证据审查。
- P_checkpoint_review：GPT-5.6 Sol / medium，仅在该 P 节点所有任务均 APPROVED 后调用一次。
- release_gate：GPT-5.6 Sol / high，仅在所有指定 P 节点均通过后调用一次。
- 普通 task_review 明确禁止 High，避免高档推理额度被日常任务消耗。
- P 节点未齐、Release 前置节点未齐时直接 HOLD，不调用更高档模型。

## 4. P节点版本产物
每个 checkpoint 自动生成：P_CHECKPOINT_REVIEW.md、VERSION_REPORT_ZH.md、COMMIT_MESSAGE_ZH.txt。
VERSION_REPORT_ZH.md 固定覆盖：节点目标、纳入任务、修改前问题、关键变化、行为影响、风控边界、测试与范围证据、修改文件、回滚方案、已知风险、P节点 Final Review、Git版本记录。

## 5. Release Gate
新增独立 release-gate 命令。Release High 只做发布门禁和跨 P 节点风险仲裁，不修改代码。自动 merge、自动 tag、真实交易权限继续保持 OFF。

## 6. 版本化配置
由于本机 .agent_hub/policy.json 被 .gitignore 忽略，新增已跟踪的 orchestrator.json -> hub_max_running_tasks=3 作为 Hub 并发上限的版本化覆盖来源，避免只在本机生效、提交后丢失。

## 7. 验证结果
- Agent Hub validate：VALID
- run-batch dry-run：可正确筛选当前 runnable task
- tests/test_agent_hub.py + tests/test_agent_orchestrator.py：38 passed
- compileall：通过
- 新增测试覆盖：互斥文件并发阻断、独立文件并行领取、Depends-On 阻断、审查档位分离、普通任务禁止 High、checkpoint HOLD、release HOLD、并发 scope 所有权识别。

## 8. 安全边界
- AUTO_MERGE=OFF
- AUTO_REAL_BUY=OFF
- AUTO_REAL_SELL=OFF
- P5_FORBIDDEN 不自动授权
- 未修改 trade_gateway.py、券商接口、凭据或真实交易开关

## 9. 已知边界
当前 batch 并行仍使用同一工作区，通过声明式 Files Allowed 所有权与 claim 互斥保护并发；尚未升级到每任务独立 Git worktree。若未来需要让不可信 Worker 在高并发下完全隔离写入，可继续升级为 worktree/sandbox-per-task 模式。

## 10. 回滚
回滚本次控制面提交即可恢复旧编排器；如需仅关闭并发，可将 orchestrator.json 中 hub_max_running_tasks、batch_default_workers、batch_max_workers 调回 1，不影响交易业务模块。
