# G02 — PAPER 恢复与对账

状态：源码完成；离线验收通过；线上快照已只读核对但差异未解释，发布门仍关闭。  
依赖：G01 `PositionFactsV2` 与 snapshot v2 契约。  
修改范围：`trading_kernel/execution/paper_adapter.py`、G02 专项测试。

## 实施前核对

- `PaperExecutionAdapter` 已有 JSON 持久化、流水重放和 T+1 当日买入拦截。
- 旧恢复逻辑只按持仓数量告警，忽略代码、成本和现金差异；重放错误会被吞掉；`entry_time` 可从不确定流水补写，存在误解锁卖出风险。
- 线上 PAPER 状态确有 51/19 差异；2026-09-24 06:13 HKT 对安装目录快照只读解析，未写入或迁移文件。

## 已实施

- PAPER 恢复现在调用 G01 snapshot v1/v2 迁移与校验；损坏、版本不支持、字段不完整、负值及空状态文件均阻断交易。
- 使用成功订单流水重放仓位和现金，逐项比对代码、数量、加权成本与现金；差异保留快照原文并设置执行阻断原因，不自动覆盖或修复仓位。
- 移除以订单时间修复未知持仓 `entry_time` 的启发式逻辑。
- 持仓读模型输出 `total_qty`、`sellable_qty`、`today_buy_qty`、`unresolved_qty`、`lots` 和 `t1_fact_status`；生产卖出门按可卖事实核验，未知数量 fail-closed。
- 新持久化快照写 v2，加载旧版时执行保守迁移。

## 验收

```powershell
python -m pytest trading_kernel\tests\test_paper_reconciliation.py trading_kernel\tests\test_paper_trading.py trading_kernel\tests\test_continuation_foundation.py trading_kernel\tests\test_t1_position_facts_v2.py -q
```

结果：28 项通过。测试覆盖 v1/v2 恢复、临时快照往返、代码/数量/成本/现金差异、不可行卖出流水、T+1 未知仓位和 fail-closed 指令阻断。  
扩大回归：包含 G01/G03/G04/G05/G09 相关用例的合并命令共 67 项通过。

## 风险与未完成验收

- **只读线上样本（2026-09-24 06:13 HKT）：** `logs/tk_reconciliation/latest.json` 的生成时间为 2026-09-24 00:03:53，SHA256 `ddcd63d3b008f6d995dc97433872b775d240ded06208135d4b730beac9a8e70b`；模式 PAPER，snapshot v2，positions/states 各 51、orders 716、`changed_count=0`。报告同时给出 `status=ALIGNED`、`ledger_status=LEGACY_MISMATCH`、snapshot-only 32、order-only 0；因此 `ALIGNED` 仅表示持仓投影与状态表一致，不能当作订单账本已对齐。根快照 `logs/paper_account_state.json` SHA256 `df14540bb1ff76762a4004208b20710cf1914f6886a72ed01c5eaa6b782cb6f1`，51 个持仓、716 条订单，文件修改时间为 2026-09-23 10:28:53。
- 716 条可用订单时间范围为 2026-05-25 至 2026-09-23；按运行报告的“BUY 增加、任一 SELL 清零、REDUCE 减量”规则，推导 19 个持仓。与快照重合的 19 个代码数量一致；其余 32 个代码在这 716 条订单中没有任何对应记录，不能据此判断是历史初始仓、流水缺失还是其他迁移来源。

| 快照独有代码 | 快照数量 | 可用订单记录数 |
| --- | ---: | ---: |
| 000526 | 100 | 0 |
| 000636 | 100 | 0 |
| 000923 | 300 | 0 |
| 000975 | 200 | 0 |
| 002199 | 400 | 0 |
| 002298 | 600 | 0 |
| 002517 | 300 | 0 |
| 002667 | 500 | 0 |
| 002879 | 300 | 0 |
| 300001 | 100 | 0 |
| 300169 | 1,000 | 0 |
| 300209 | 100 | 0 |
| 300285 | 100 | 0 |
| 300469 | 100 | 0 |
| 300510 | 1,400 | 0 |
| 300515 | 300 | 0 |
| 300540 | 100 | 0 |
| 300643 | 300 | 0 |
| 300688 | 200 | 0 |
| 301012 | 200 | 0 |
| 301273 | 100 | 0 |
| 600243 | 1,500 | 0 |
| 600379 | 400 | 0 |
| 600938 | 100 | 0 |
| 601898 | 300 | 0 |
| 603123 | 500 | 0 |
| 603956 | 800 | 0 |
| 605319 | 200 | 0 |
| 688389 | 400 | 0 |
| 688681 | 300 | 0 |
| 920225 | 300 | 0 |
| 920701 | 400 | 0 |

- 每条线上订单行只有 `action/code/order_id/price/request_id/size_pct/timestamp/volume`，没有成交/拒绝状态。按严格数量重放所有 BUY/SELL 会遇到 297 条“卖出量超过账本持仓”，说明此历史数组不能直接视为完整、已成交的 fill ledger；不能据它自动改仓或宣称现金对平。
- **历史对账归档复核（只读）：** `reconciliation_20260922.jsonl` 解析 1,628 行、无坏行，`ledger_status=LEGACY_MISMATCH` 为 1,628/1,628；持仓数在 55–63、订单数 704–712。`reconciliation_20260923.jsonl` 解析 973 行、无坏行，`LEGACY_MISMATCH` 为 973/973；持仓数在 51–55、订单数 712–716。两份归档的所有订单对象均无 `status`、`execution_status`、`filled_qty` 或 `fill_status` 字段。它们证明差异连续存在，但仍不是成交事实源，无法解释 32 个快照独有代码。
- 归档 SHA256：9/22 `8be194cb6cc2791495be7d44ec96b4f5ff3dc228ed9efdad108ebc2ebbe0539c`（231,202,082 bytes）；9/23 `060425a43f2152314a4041a2e67ec19ffdab25b3679f33740360aecd90da4416`（161,338,359 bytes）。只读解析/哈希未改动归档。
- 该线上报告缺少 `paper_execution_ready`，且运行 EXE 与当前源码提交没有可核验指纹对应；本次采样只证明差异存在，不证明修复后的源码已在运行。
- 历史流水若缺成交、包含费用/分红/资金划转，现金或成本对账会阻断 PAPER；这需要解释/补齐权威事件，不应放宽比较来掩盖差异。
- 线上零差异、现金完整性、T+1 批次可卖事实和快照 v2 修复后的真实 EXE 行为均未验收。
- 回滚检查点：仅回退本任务源码与专项测试；不得重置、改写或迁移生产状态文件。
