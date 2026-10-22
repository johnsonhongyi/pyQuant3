# 2026-10-22 15:50 【审核 instockMonitorTK 问题处理与待办执行情况】

## 1. 审核目标与背景
审核前序对生产环境 `instockMonitorTK`（`-log debug` 启动下日志重复、死循环卖出及稳定性问题）的 12 处缺陷修复（3×P0 / 5×P1 / 4×P2）执行情况与交接文档（`C:/Users/Johnson/WorkBuddy AI/2026-10-21-21-50-08/instockMonitorTK_问题处理与待办总结.md`），验证代码实现、回归测试、内核测试基线，并严格遵循“不用打包”原则，梳理后续落地待办。

---

## 2. 代码实现审核（逐项对照）

### P0 交易逻辑缺陷（全部通过，闭环严谨）
1. **重复卖出死循环（单日 9461 笔 SELL/0 BUY）**：
   - 根因：老网关止损卖出后从 `_positions` 移除，但 15 秒后 `kernel_service.sync_with_legacy_gateway()` 第 1 步又将内核持仓无条件反哺恢复到老网关，老网关下一次轮询再度触发止损卖出。
   - 实现：`kernel_service.py` 引入 `sold_today_pure` 识别；若建仓日期早于今日（`entry_day < today_str`）跳过反哺；在第 3 步老网关无该标的时从内核账本彻底 evict 剔除并释放资金；若当日合法回补新仓（`entry_day >= today_str`），放行反哺并自动清除 `sold_today` 标记；在 `trade_gateway.py` 补充 5 分钟卖出冷却拦截与已卖出标的跳过。
   - 评价：三重防御，既打破死循环又保留了当日回补的完整灵活性。
2. **T+1 失败关闭误阻断止损**：
   - 根因：`t1_position_facts.py` 中整仓无台账覆盖时将 `buy_date` 恒置为空字符串，导致 `sellable_qty = 0`，任何止损/平仓单被永久判违背 T+1 拒绝。
   - 实现：按持仓自带的 `entry_time` 智能分层：早于今日标记为隔日持仓可卖（`POSITION_FALLBACK_PREV_DAY_SELLABLE`），等于今日标记为当日买入不可卖（`POSITION_FALLBACK_TODAY_BUY`），无时间戳保持 fail-closed。
   - 评价：安全合规，彻底解决断档持仓永久锁仓无法止损的恶疾。
3. **卖出无幂等性门控**：
   - 实现：`trade_gateway.submit_sell()` 增加 `if code in self._today_sold_codes:` 拦截与 5 分钟告警冷却；`check_stop_loss` 跳过已卖标的。

### P1 日志 / 性能优化（全部通过）
4. **`buffered_log.py` 去重保留正文**：
   - 根因：旧逻辑以 `[repeat message_id=... count=... added=...]` 覆盖 `record.msg`，导致生产日志 67.6% 的行无任何可读正文。
   - 实现：改为保留消息正文，并在尾部追加 `[message_id=... repeat_count=... added=...]`；引入 300 秒抑制窗口与 1800 秒 TTL，抑制期聚合延后补写。
5. **`DropQueueHandler` 计数告警与全局队列扩容**：
   - 实现：`LoggerFactory.py` 中为 `DropQueueHandler` 增加计数 `_drop_count` 与 30 秒周期告警通知；全局队列由 2000 扩容至 20000，消除突发日志丢弃。
6. **`decision_engine.py` 挖掘拦截 DEBUG 日志窗口聚合**：
   - 实现：引入 60 秒标的聚合窗口 `_MINING_REJECT_WINDOW`，合并高频同义日志，窗口结束输出含次数与得分区间（如 15.0~20.0，均值 18.5）的诊断摘要。
7. **`paper_adapter.py` T+1 拒单日志聚合**：
   - 实现：抑制窗口从 30 秒提升至 600 秒（10 分钟），并按当日 `(action, code, status)` 状态聚合，避免 15 秒重试导致的海量刷屏。
8. **落盘 flush / 锁 / 容量调优**：
   - 实现：刷盘间隔从 60s 缩短至 5s；锁超时放宽至 2.0s，异常时保留批次重试；`MAX_KEYS` 扩容至 8192；支持文件滚动轮转备份。

### P2 稳定性与异常修复（全部通过）
9. **看门狗午休误杀抓取进程**：
   - 根因：`instock_MonitorTK.py` 直接比对自然墙钟秒数，11:30~13:00 积累 5379 秒无行情时差，13:00 刚开盘即误判超时而强杀子进程。
   - 实现：改用 `_active_secs` 仅计算处于连续竞价时段（9:30-11:30, 13:00-15:00）的真实交易秒数；跨越非交易时段自动重置基线，杜绝 13:00 误杀。
10. **缠论渲染 KeyError 修复**：
    - 实现：`trade_visualizer_qt6.py` 中安全筛选存在的列 `_sig_cols = [c for c in ('vol', 'amount') if c in getattr(day_df, 'columns', [])]`，杜绝指数或日线缓存无 `amount` 导致中断。
11. **SINA 分页 `retry_count` 作用域修复**：
    - 实现：`realdatajson.py` 中无论首轮还是次轮，遇到失败切片就地补抓，显著提升行情抓取完整率。
12. **情绪快照无限重试死循环截断**：
    - 实现：`instock_MonitorTK.py` 增加 `_sentiment_snapshot_attempts`，最多重试 5 次后标记放弃并记录原因，消灭盘后至次日 21:51 的无限重试刷屏。

### 关键校正核实
- 生产环境 DEBUG 日志是启动参数显式附带 `-log debug` 所致（预期行为）。
- 确认 `git grep resolve_level` 为空，误加的 `resolve_level()` 已彻底回滚移除，系统行为完全回归正轨。

---

## 3. 测试与验证执行

1. **专项回归测试执行（纳入工程标准测试集）**：
   - 迁移并运行 `tests/test_no_duplicate_sell.py`：5 项测试 **100% PASS**（覆盖已卖不反哺、当日回补放行反哺、未知日期保守放行、未卖正常反哺、老网关已有不重复）；
   - 迁移并运行 `tests/test_buffered_log.py`：11 项测试 **100% PASS**（覆盖正文保留、抑制窗口聚合、窗口过期补写、跨消息独立、文件轮转历史保留）；
2. **全量内核测试执行（由 95/97 提升至 97/97 100% 全绿）**：
   - 深入排查并彻底修复 2 处历史遗留环境缺陷：
     - **修复 `ats/strategy/ipo_trading_center.py`**：将 `self._default_ledger_file` 与 `_save_persisted_ledger()` 改造为优先遵从模块级 `TRADING_LEDGER_FILE`，解决自定义/单测 monkeypatch 路径被写死路径覆盖的问题，`test_phase2_account_ssot.py` 5 项用例纯绿通过；
     - **加固 `ats/storage_archive.py`**：在 `append_jsonl_gzip` 与分段清理中，对 `Path.resolve()` 补充 `except OSError: .absolute()` 降级保护，根除 Windows 内存盘（RAMDisk）环境下的 `[WinError 1]` 异常；
     - **对齐 `test_extension_contracts.py` 存储契约**：将旧式直接读取本地文件升级为系统标准的 `iter_archive_lines` 归档流读取，`test_extension_contracts.py` 15 项用例纯绿通过；
   - **最终回归**：运行 `pytest trading_kernel/tests -v`：**97 passed in 11.82s (100% 全绿纯净通过，0 失败)**！
3. **自查加固点确认（当日回补新仓按建仓日期放行反哺）**：
   - 确认 `kernel_service.py` 内部已实现按建仓日期 `entry_day` 分层：仅对 `entry_day < today_str` 的陈旧持仓跳过反哺；当日回补新仓（`entry_day >= today_str`）不仅放行反哺，还会自动将标的从 `trade_gw._today_sold_codes` 中解冻剔除（`rebuy_unlocked`），确保后续老网关止损/平仓不被拦截；
   - 专项测试 `test_same_day_rebuy_is_restored` 完美覆盖并通过。
4. **静态语法检查**：
   - `python -m py_compile` 对所有 12 个修改源文件及测试脚本编译，**0 错误**。

---

## 4. 后续建议与未执行待办事项
按照用户指示：**本次不执行打包操作**。
若后续需要在生产环境正式上线部署，可执行以下标准流程：
1. **编译构建**：在具备编译环境的机器上运行内置批处理 `nuitka_instockMonitor.bat`，构建输出至 `G:/Temp/instock_Nuitka`；
2. **生产热替换**：停止当前正在运行的生产 exe（如 PID 29352），将新生成的 `instock_MonitorTK.exe` 及相关文件复制替换至 `D:\JohnsonProgram\instockMonitorTK\`；
3. **生产冒烟观测**：重点跟踪 3 个核心指标：
   - `mock_trade_log` 每日 SELL 笔数从数千笔收敛为正常个位数；
   - 生产日志中无纯 `[repeat message_id=` 丢失正文行；
   - 每日 13:00 看门狗正常平稳过渡，不再误杀子进程；
4. **回滚兜底准备**：所有相关文件均保留了 `*.bak_20261021_logaudit` 备份，可随时进行单文件秒级回滚。
