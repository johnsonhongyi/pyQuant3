# G04 — 会话时钟与候选确认

状态：源码与离线验收完成；线上观察未执行。  
依赖：G00 冻结的候选语义。  
修改范围：`ats/session_clock.py`、`ats/candidate_cache.py`、G04 专项测试。

## 实施前核对

- CandidateCache、盘前 seed 隔离、连续帧确认、间隔超时、重复/乱序过滤和按日期清缓存已存在。
- 原会话时钟使用主机本地时间；带时区观察值会按运行机器转换；`HH:MM[:SS]` 观察时间隐式读取系统日期，回放受主机状态影响。

## 已实施

- 会话时间统一解释为中国市场 `UTC+08:00`；带时区 datetime 先换算为市场时间，naive datetime 保持为市场墙上时间。
- CandidateCache 支持可注入时钟；无时间输入及纯时间字符串不再依赖运行主机本地时区。
- 保留原有候选 API 默认值和 seed/确认行为，重复或乱序帧不增加确认数，午休与跨日重置序列。

## 验收

```powershell
python -m pytest tests\test_session_clock.py tests\test_signal_pipeline_hardening.py tests\test_p1_ledger_single_entry_hardening.py -q
```

结果：24 项通过。覆盖 UTC 转市场时区、午休边界、注入时钟、盘前 seed、重复/乱序帧、超时和跨日清理。

## 风险与未完成验收

- 市场时区采用固定 UTC+08:00，适用于 A 股交易时间；交易日节假日需由上游行情/交易日历提供，不由此时钟推断。
- 未用线上行情时间戳验证各数据源的时区编码；该观察仍属于发布验收门。
- 回滚检查点：只回退上述时钟/候选文件和 G04 专项测试，不清理生产候选或信号记录。
