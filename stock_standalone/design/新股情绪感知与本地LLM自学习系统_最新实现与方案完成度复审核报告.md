# 新股情绪感知与本地 LLM 自学习系统：最新实现与方案完成度复审核报告

> 审核日期：2026-09-28
> 对照方案：v1.1-R9 最终审核修订版
> 代码基线：HEAD 420ae047af43624ebb7f2f2099e1a792628da4c8（2026-09-28 09:53 +0800）
> 审核范围：当前代码、配置、仿真产物、数据就绪快照、任务记录与方案书；本轮未运行测试，未修改生产代码。

## 一、复审裁决

最新实现确实补上了双 CLI Provider、运行时工厂、请求脱敏、后台 Worker 和合成仿真入口，属于有效的基础设施里程碑。但用户提供的上一版综合报告有过时数据及“实现完成”范围扩大问题，不能直接作为生产验收结论。

- **代码实现结论：**有条件通过基础设施代码审查；远端 Provider 的提示词边界与 OS 隔离证据仍需补齐。
- **方案完成度结论：**未完成。Gate 正向放行、真实数据覆盖、完整回放、UI/人工复核闭环与模型训练晋级都没有形成端到端验收证据。
- **生产准入结论：**继续 Fail-Closed。当前配置仍关闭 AGY/Codex Provider 和远端调用；Gate 上下文缺失时阻断；数据快照标记 UNREADY，交易与 LLM 授权均为 false。

## 二、先纠正评估基线与过时声明

| 项目 | 复核结果 |
|---|---|
| “暂存区最新改动 18 个核心文件，+1049/-158” | 数量与差异属实，但这 18 个文件已包含在 HEAD 420ae047；当前暂存区只有任务记录与 gemini.md 两项文档变更。 |
| 41 项指标就绪度 6/41 | 已过时。data/ipo_learning/acquisition.latest.json 于 2026-09-28 02:02:51 UTC 生成，记录 15/41、status=UNREADY。该数值是快照，不能外推为之后的实时状态。 |
| “双 CLI 端到端已跑通” | 有限成立。仓库内 9 份仿真 manifest 来自 2026-09-27，早于当前 HEAD：3 份 result_status=OK、2 份 UNAVAILABLE、2 份 NO_RESULT、2 份 FAILED。成功项使用合成数据，Gate 均在 Gate 0 BLOCK，且 manifest 未绑定当前源码提交哈希。它证明曾有 CLI 返回结果，不证明当前提交已复现、Gate 正向放行或生产隔离验收通过。 |
| “全系统 350 项测试通过” | 当前材料不可独立核实。20260928_0948_task.md 与 gemini.md 有通过声明，但没有保留测试命令、原始输出、收集数和提交基线。本轮没有重跑测试。方案中的 17 组、至少 324 项是规划目标，不是测试执行证据。 |
| “41 项合成数据证明真实数据完整” | 不成立。仿真写入的 41 个字段是合成观测；真实快照仍为 UNREADY。 |
| “完成离线自学习” | 不成立。已有候选校验、SFT/DPO 数据集构建、时间切分、影子评估及人工晋级/回滚证据校验；没有实际权重训练器，也没有自动更换运行模型的代码路径。 |

方案书标题页当前版本为 v1.1-R9。其第捌节和阶段说明明确把完整数据字典、回放、隔离压测、UI/告警和模型晋级列为后续准入工作；不能将 Provider 接口存在等同于系统需求全部完成。

## 三、已完成且有源码依据的功能

1. **双 CLI Provider 基础实现**：backend_factory.py、codex_cli_backend.py、antigravity_cli_backend.py 与 cli_paths.py 提供工厂、Codex/AGY 命令适配和 Windows 路径探测。Codex 调用使用 read-only sandbox、Schema 参数和 stdin 输入；这是调用构造，不是 OS 网络出口或文件系统隔离验收。
2. **运行时旁路骨架**：llm_worker.py、runtime_service.py、control_thread.py 与 worker_protocol.py 实现隔离 Worker、受限 JSON IPC、请求排队和结果状态；当前配置没有授权其生产运行。
3. **结构化 context 白名单投影**：remote_sanitizer.py 按 Agent policy 投影 context 并进行预算/契约校验；provider_preflight.py 具备配置与隔离前置项检查。真实 Windows Job Object、网络出口和无工具权限的运行证据尚未提供。
4. **合成仿真工具**：run_ipo_llm_simulation.py 可写入合成观测、生成 Gate 快照、尝试 Provider 请求并记录 manifest；其 Gate 检查明确要求 BLOCK，因此它不是 Gate ALLOW 或交易派单测试。
5. **D1-D3 成熟度证据代码**：ipo_outcome_labels.py 按传入的交易日历挑选上市后前三个交易日，并在日历或日线不足、D3 尚未成熟时不生成成熟标签；当前实现不能独立证明上游交易日历完整无缺。
6. **离线数据集准备**：offline_learning.py 已实现候选/人工复核证据校验、SFT/DPO 数据集生成与时间向前切分，以及影子评估和人工生命周期证据校验。生命周期证据函数不执行训练或运行时切换。
7. **UI/运行状态基础**：ipo_learning_console.py 和运行入口有控制台与状态查看改动；本轮未获得 UI 人工复核闭环或 ATS 实盘影子压测的验收记录。

## 四、阻断上线的审核问题

### P1 — Provider 脱敏没有覆盖 prompt

codex_cli_backend.py 与 antigravity_cli_backend.py 先对 request.context 调用 build_remote_safe_request，再把 request.prompt 原样拼接到发送文本。worker_protocol.py 只检查 prompt 类型、长度与 IPC JSON 约束；control_thread.py 的 submit_request() 接受一般 Mapping。当前内置 request producer 使用固定提示词，且 Provider 配置关闭，因此尚未形成当前生产出域；但通用请求入口没有阻止其他调用方放入原始行情、身份数据或密钥。

**准入条件**：只允许固定且版本化的提示词模板；拒绝任意调用方 prompt，或将 prompt 拆成经 schema/allowlist 验证的结构化字段；增加数据泄漏拒绝测试后再审批远端调用。

### P1 — 仿真接受标志不能代替隔离控制证明

仿真工具的 _simulation_authorization() 将 process-tree、tool-access、remote-egress isolation 的 accepted 标志设为 true，并以 SIMULATION_ONLY 生成临时接受材料。源码同时注明 destination 只是标记值，不形成 OS 网络出口控制证明。因此仿真可证明测试夹具下的流程行为，不能证明真实机器已实施网络、工具、工作目录及进程树隔离。

**准入条件**：生产接受材料必须来自实际 OS 控制配置与独立验收记录，不能由仿真脚本自签；记录目标、策略版本/哈希、进程回收和出网阻断实测结果。

### P2 — AGY 命令行暴露 prompt，CLI 输出没有显式大小上限

antigravity_cli_backend.py 将完整 prompt 放在 -p 命令行参数中，可能暴露于进程命令行观察，并受 Windows 命令行长度限制。两个 CLI 适配器都使用 capture_output=True；代码路径未见显式 stdout/stderr 字节上限。须验证超时后整个子进程树回收、输出有界及临时 Schema 文件清理。

**准入条件**：优先使用经验证的 stdin/安全 IPC 传输；为输出和错误通道设硬字节限额；超时或超量时终止并回收进程树；通过 Windows 集成测试验证。

### P1 — Gate Provider 当前无法组装正向上下文

ipo_gate_context_provider.py 的 __call__() 将 LRRM、Regime、T1 Carry、ListingAnchors、VWAP 与 RiskGate context 置为 None，并使用 intraday_low=0.0、listing_age_sessions=0。由此当前代码可证明缺失输入会阻断，不能证明完整真实数据会正确组装并正向通过 Gate 0-5。仿真工具也主动断言 Gate 0 BLOCK。

**准入条件**：完成指标到强类型上下文的映射、来源/时间戳/TTL/哈希检查、实时 RiskGate 注入；在隔离回放中同时验证预期 BLOCK 与合法 ALLOW，且未经授权永不产生 ENTRY 派单。

### P2 — 数据快照仍不具备上线就绪度

最新快照为 15/41，状态 UNREADY。应逐指标完成来源、采集时间、可用时间、TTL、缺失策略、拒绝原因与配置哈希；禁止把“已定义契约”或合成值计入真实数据 READY。

### P2 — 回放、标签、界面与模型闭环还缺验收证据

- 全输入 Historical Cut-Off 回放需要覆盖方案列出的代表性新股与目标日期范围，并产出 13 项报表；未来数据泄漏数为零等硬门槛目前没有本轮证据。
- D1-D3 日历逻辑使用传入日历；还需验证日历源完整性、缺失交易日、重复/错位 K 线、时区边界和 15:00 收盘边界。
- 人工标签复核和复盘 Agent 请求流尚未提供日常闭环验收记录。
- 离线训练、候选权重产物评估、人工晋级、运行时切换、回滚演练尚未完成；现有 lifecycle evidence 只是校验/记录。
- 300ms 主轮询零漏期、Qt 心跳延迟增量 ≤5ms、Worker 崩溃/队列满/超时/输出超限/残留进程等压测结果未附原始记录。

## 五、分阶段完成度裁定

| 方案阶段 | 复审状态 | 依据与剩余验收 |
|---|---|---|
| Stage 0：基础设施与契约 | 部分完成 | Provider、IPC、契约与状态快照已有实现；真实数据 15/41 且 UNREADY，来源清单、隔离证据与性能基线未齐。 |
| Stage 1：门禁与算法闭环 | 阻断/未验收 | Gate 规则与失败关闭路径存在；上下文 Provider 关键字段仍为 None，RiskGate 缺失即阻断，尚无可信正向 ALLOW 与派单闭环。 |
| Stage 2：只读 Agent 与经验沉淀 | 部分完成 | Provider/Worker/仿真代码可调用；生产授权关闭，数据检索、真实回放证据与请求安全边界未验收。 |
| Stage 3：界面因果钻取与提示 | 部分/未验收 | 控制台已有代码；完整状态展示、告警、日常人工标签复核流程与性能验收记录未确认。 |
| Stage 4：离线偏好对齐与微调 | 部分完成 | SFT/DPO 数据集构建、拆分与影子/生命周期证据校验存在；训练执行、候选模型效果评测和运行时晋级/回滚尚未闭环。 |
| 测试矩阵：17 组、至少 324 项 | 规划未验收 | 有既有测试和任务记录声明；缺少可复核的本基线完整测试报告，不能用单一总数代替逐组覆盖。 |

## 六、后续工作顺序与验收门槛

1. **先修 Provider 数据边界**：固定/校验 prompt；移除 AGY 命令行明文 prompt；为 stdout/stderr 加上限；实测 Windows 进程树回收和 OS 网络/工具隔离。完成前保持所有远端 Provider 关闭。
2. **补齐真实数据生产者**：按 41 项契约逐字段接入与记录 source_id、source_version、observed_at、available_at、TTL、拒绝原因和配置哈希；快照达到方案准入定义且不存在伪 READY。
3. **完成 Gate 强类型映射**：由已校验数据生成 LRRM/Regime/Carry/双锚/VWAP/RiskGate context；以隔离数据集证明预期 BLOCK/ALLOW、价格边界、风险限额和最终派单均正确。
4. **完成历史回放及标签闭环**：覆盖方案指定样本与日期范围；验证新闻/公告/行情/向量的 cutoff；产出 13 项指标，future_leakage_count=0；核验 D1-D3 日历完整性与人工复核流程。
5. **完成生产影子与性能验收**：先只读影子运行，确认主轮询无漏期、Qt 延迟阈值、旁路熔断和故障回退；保存环境、配置哈希、样本范围、原始指标和审计日志。
6. **再建设模型训练晋级流程**：实现并验收训练执行器、数据/权重哈希、独立评估集、基线对比、人工审批、灰度/切换与回滚；未经人工晋级不改运行模型。
7. **发布逐组测试报告**：按方案 17 组矩阵列出用例数、执行命令、通过/失败/跳过、环境与 commit；把失败项作为准入阻断，不以汇总数字替代覆盖。

## 七、工作区与证据限制

- 当前 18 文件代码差异属于 HEAD；当前暂存区是 20260928_0948_task.md 与 gemini.md 的文档变更。本报告新增为独立审核文档，不改写上述已有暂存内容。
- 本报告根据当前快照与仿真目录作出状态判断；数据 READY 数、运行配置和产物会随工作区更新，应在下一次准入评审重新取证。
- 本轮没有运行 pytest 或修改生产代码，因此没有把历史任务记录中的测试通过声明当成本轮实测结论。
