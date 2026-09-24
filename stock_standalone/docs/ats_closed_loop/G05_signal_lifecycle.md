# G05 — 信号账本与生命周期

状态：源码与离线验收完成；线上行为及 UI 视图一致性未验。  
实施前核对：`LedgerUpdateService`、`SignalLedger`、展示快照投影和独立 `SignalLifecycle` 均已存在。确认缺口是生命周期状态机未连接真实账本；此前已完成快照投影不新增候选、服务标记不能绕过候选门禁、双 VWAP 破位当日不能凭旧标签复活。

## 本次补齐

- `SignalEntry` 持有生命周期实例；真实账本记录、晋级和更新会同步进入状态机。
- TDX 确认晋级同步记为生命周期事件；生命周期快照含状态、修订号和历史转移。
- 转移历史记录原因、事件时间、snapshot_id 和 revision；缺失时间保留状态机生成的本地时间。
- `INVALIDATED` 在同一账本周期内为终态，后续报价不能把条目重新晋级。
- 旧快照仍由既有跨日恢复逻辑重建为 RADAR，不伪称恢复了原 Lifecycle 对象；当日完整持久化恢复需在实际快照装载链路中另行验收。

## 验收

```powershell
python -m pytest tests\test_p1_ledger_single_entry_hardening.py tests\test_signal_pipeline_hardening.py -q
```

结果：22 项通过。G01–G05/G09 合并回归：67 项通过。覆盖真实账本生命周期写入、状态快照序列化、TDX 晋级、双 VWAP 终态保护与既有候选门禁。

## 未覆盖

- 未连接线上运行数据或生产 DB；未证明当前 EXE 使用该源码。
- UI 多视图状态一致性与过期 BUY 拦截归 G10。
- 快照加载目前是前日候选恢复，不是同一运行周期内的完整事件恢复。
