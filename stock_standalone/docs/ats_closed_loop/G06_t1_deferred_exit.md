# G06 — T+1 延期退出与 ATS 仲裁

状态：部分实施；离线专项通过，历史失败专项与线上闭环未验。  
实施前核对：原有 T+1 执行硬锁、同代码 EXIT 压 BUY、底台破位与高潮退出触发条件、退出引擎和原子账本保存均已存在。已确认的缺口是零可卖数量时部分路径丢弃意图，交易中心持仓同步重建对象会丢失延期状态。

## 已补齐

- 新增持仓退出状态：`EXIT_DEFERRED_T1`、`NEXT_DAY_EXIT_READY`、`SUBMITTED`、`FILLED`、`PARTIAL`、`REJECTED`。
- 零可卖数量时保留原始动作、数量、退出原因/规则、触发时间及 T+1 阻断原因，并写入本地账本；直接退出引擎、底台止损、高潮和其他聚合退出均经过统一零可卖过滤。
- PAPER 持仓刷新会保留独立的 `pending_exit_intents`；次日 authoritative sellable_qty 大于零后恢复为可执行退出。状态为 SUBMITTED 但内存指令丢失时可按稳定 directive_id 重建。
- `IPOOrderDirective` 生成稳定 directive_id 和审计 envelope；退出记录保存 gate、提交、拒绝或成交结果。T+1 物理锁仍在执行端保留。
- 2026-09-24 补充同批决策上下文写入：指令按同一代码匹配输入 signal，并记录本批 sentiment.tide_state 与实际 strategy_tag；跨日过滤状态沿 TradePlan 传入。BUY 缺少跨日计算时不填充伪状态，发布日报会将其识别为未覆盖。
- 直接生成的底台/VWAP 止损与高潮退出指令携带 `exit_rule_id`、规则层级，并进入审计 envelope；隔离账本回归实际走交易中心生成路径验证底台 CRITICAL 卖出和高潮 LIMIT 卖出。
- 未把 TK 拒单伪报成成交；G06 集成夹具实际观察到 `TK_PAPER_REJECTED`，并验证 ATS 留下 REJECTED 与原因。

## 验收

```powershell
python -m pytest tests\test_g06_deferred_exit.py tests\test_channel_secondary_buy_strategy.py -k "g06 or t1_blocks_normal_reduce or catastrophic_exit or t1_eligible_partial or t1_blocks_full_rotation or ledger_reload or pending_exit_prevents or t1_generates_portfolio_exit" -q
```

结果：8 项通过。G01–G05/G09 加 G06 延期退出专项合并：69 项通过。

补充回归：`python -m pytest tests/test_g06_deferred_exit.py -q`：当前 3 项通过，覆盖延期恢复/TK 拒绝审计、直接止损/高潮指令规则身份，以及账户级 PAPER 对账不一致进入部署门并阻断执行。延期恢复用例显式注入 ALIGNED 前置状态，以继续验证下游 TK 拒绝审计。

后续定向复核：`pytest tests/test_channel_secondary_buy_strategy.py -k "test_03_breakdown_base_low_invalidated or test_07_higher_low_stop_triggers_exit_all or test_15_catastrophic_exit_cannot_bypass_t1_physical_lock or test_36_t1_generates_portfolio_exit_and_leader_defense" -q`：4 passed。它们覆盖底台破位识别、结构止损、T+1 物理锁及 T1 组合退出；不能替代历史 118/2 失败夹具的同版本复现。

## 未完成与限制

- 尚未在同一代码版本重跑历史“底台破位/高潮退出 118 passed、2 failed”专项，不能据此宣告修复原失败。
- 本轮 15 文件集成回归包含完整 `test_channel_secondary_buy_strategy.py`，pytest 全部退出码 0；另对底台破位、高低点止损、T+1 物理锁和组合退出 4 项定向复验，4 passed。此结果仍不等同于原始 118/2 历史失败夹具复现。
- 实际 TK PAPER 拒单场景已验拒绝审计；没有证明次日执行在真实 TK 账户中成交或部分成交。线上对账、构建指纹和 2–3 日全链路观察均未做。
- 运行数据库、日志和生产持仓保持未读取/未写入；不涉及券商下单。

当前工作树复验：按本卡筛选命令重跑，9 passed。该组覆盖延期恢复、拒绝审计、T+1 物理锁、全仓轮动阻断及组合退出生成；仍不能替代历史 118/2 失败夹具或多日 TK PAPER 证据。

2026-09-24 G15 前复核：优化计划引用的原始专项文件 `test_ipo_vwap_bottom_base_preorder.py`、`test_t1_and_signal_display.py`、`test_subnew_intraday_volume_normalization.py`、`test_tradeplan_structural_rr.py`、`test_subnew_executable_gate.py` 均不在当前工作树，无法按原命令复现历史 118/2。当前工作树现有底台破位、结构止损、T+1 物理锁和组合退出 4 项复验通过；`tests/test_g06_deferred_exit.py` 3 项通过（pytest 退出码 0）。这验证当前可用回归，不证明两个历史失败已经在原夹具上修复。
