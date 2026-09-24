# G11 真实链路影子采集

状态：ATS 候选分析/仲裁与显式隔离 TK PAPER 注入源码已实现；离线验收通过；真实行情多日运行未做。实施前核验原脚本每轮固定写入 000001 样例、`directive_count=0`，并静默忽略日报写入失败。

现在 `--codes` 指定的股票由 IPO VWAP 检测器读取实时/缓存行情，经过 CandidateLedger 与 ATS 赛马/仲裁；信号数、指令数从组件结果统计。未提供代码时运行退化为 DEGRADED，避免伪造输入。报告逐轮追加 JSONL，写入失败标 DEGRADED。

**隔离执行：** 默认不连接 TK。非 dry-run 若未传 `--isolated-paper-state-dir`，运行器在行情扫描前写出 `DEGRADED / ISOLATED_PAPER_STATE_REQUIRED` 并退出，避免将未完成的 ATS-only 轮次记成健康影子轮次。传入目录后，规范化路径必须是 `--report-dir` 的子目录；TK PAPER 快照、审计、对账及 ATS 影子账本均写入该隔离目录，且服务初始模式固定为 PAPER。ATS 执行器和统一账户 Gateway 显式注入该服务，不调用全局 `get_kernel_service()`。逐条日报保存 directive/request/order/execution ID、结果状态和拒绝原因，并记录 Git commit、干净状态、构建指纹及冻结 EXE SHA256（源码运行不提供 EXE 哈希，发布门会拒绝）。路径越界会拒绝启动，真实券商适配器不在执行路径中。

**冻结版入口：** 构建后的 `ATS_Terminal.exe --shadow-live --help` 由 `run_ats.py` 转发到同一 runner；实际隔离运行需显式给出 `--codes`、独立 `--report-dir` 和其下的 `--isolated-paper-state-dir`。冻结 EXE 的 SHA256 随每轮报告记录，G14 只接受同一冻结构建产生的连续日报。此入口已做帮助路由检查，尚未在真实冻结包上验收。

**离线验收：** `python -m pytest tests/test_g11_shadow_runner.py -q`：8 passed。覆盖无代码 dry-run 必须 DEGRADED、非 dry-run 必须显式隔离 PAPER 状态目录、隔离执行器注入、报告目录边界、显式 Paper state path、临时 TK PAPER 服务，以及流水异常必须写出 DEGRADED 报告。G07 轮动/请求关联 3 passed，Gateway 幂等契约 7 passed；未调用默认全局服务，也未提交真实委托。离线测试不证明实时行情或运行态连续性。

**串行范围交接：** G02/G07/G06 离线源码工作后，将 `paper_adapter.py`、`kernel_service.py`、`unified_paper_account.py`、`ipo_trading_center.py` 的最小可选注入接口串行交由 G11；默认构造与原调用保持原行为。`py_compile` 与 `git diff --check` 通过。生产 DB/账户未访问，线上账户及券商均未连接。

仍需在明确隔离的运行环境中使用真实行情连续运行 2–3 个交易日，复核每条 ATS 指令与 TK 结果、报告健康度、内存和 UI/IPC 指标。未取得该报告前，G11 和整体发布门保持未完成。
